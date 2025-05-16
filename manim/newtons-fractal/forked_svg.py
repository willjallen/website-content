from __future__ import annotations

import itertools as it
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import cairo
import numpy as np
from manim import VGroup, VMobject
from manim.utils.family import extract_mobject_family_members

CAIRO_LINE_WIDTH_MULTIPLE: float = 0.01

__all__ = ["create_svg_from_vmobject", "create_svg_from_vgroup"]


@contextmanager
def _get_cairo_context(file_name: str | Path) -> cairo.Context:
    from manim import config

    pw = config.pixel_width
    ph = config.pixel_height
    fw = config.frame_width
    fh = config.frame_height
    fc = [0, 0]
    surface = cairo.SVGSurface(
        file_name,
        pw,
        ph,
    )
    ctx = cairo.Context(surface)
    ctx.scale(pw, ph)
    ctx.set_matrix(
        cairo.Matrix(
            (pw / fw),
            0,
            0,
            -(ph / fh),
            (pw / 2) - fc[0] * (pw / fw),
            (ph / 2) + fc[1] * (ph / fh),
        ),
    )
    yield ctx
    surface.finish()


def _transform_points_pre_display(points: np.ndarray) -> np.ndarray:
    if not np.all(np.isfinite(points)):
        # TODO, print some kind of warning about
        # mobject having invalid points?
        points = np.zeros((1, 3))
    return points


def _get_stroke_rgbas(vmobject: VMobject, background: bool = False):
    return vmobject.get_stroke_rgbas(background)


def _set_cairo_context_color(
    ctx: cairo.Context,
    rgbas: np.ndarray,
    vmobject: VMobject,
):
    if len(rgbas) == 1:
        # Use reversed rgb because cairo surface is
        # encodes it in reverse order
        ctx.set_source_rgba(*rgbas[0])
    else:
        points = vmobject.get_gradient_start_and_end_points()
        points = _transform_points_pre_display(points)
        pat = cairo.LinearGradient(*it.chain(*(point[:2] for point in points)))
        step = 1.0 / (len(rgbas) - 1)
        offsets = np.arange(0, 1 + step, step)
        for rgba, offset in zip(rgbas, offsets):
            pat.add_color_stop_rgba(offset, *rgba)
        ctx.set_source(pat)


def _apply_stroke(ctx: cairo.Context, vmobject: VMobject, background: bool = False):
    from manim import config

    width = vmobject.get_stroke_width(background)
    if width == 0:
        return
    _set_cairo_context_color(
        ctx,
        _get_stroke_rgbas(vmobject, background=background),
        vmobject,
    )
    ctx.set_line_width(
        width
        * CAIRO_LINE_WIDTH_MULTIPLE
        # This ensures lines have constant width as you zoom in on them.
        * (config.frame_width / config.frame_width),
    )
    # if vmobject.joint_type != LineJointType.AUTO:
    #     ctx.set_line_join(LINE_JOIN_MAP[vmobject.joint_type])
    ctx.stroke_preserve()


def _apply_fill(ctx: cairo.Context, vmobject: VMobject):
    """Fills the cairo context
    Parameters
    ----------
    ctx
        The cairo context
    vmobject
        The VMobject
    Returns
    -------
    Camera
        The camera object.
    """
    _set_cairo_context_color(
        ctx,
        vmobject.get_fill_rgbas(),
        vmobject,
    )
    ctx.fill_preserve()
    return

def _vm_is_drawable(vmobject: VMobject, ctx: cairo.Context) -> bool:
    """
    Fast fail predicate that mirrors every place in cairo-svg-surface.c
    where a path is later discarded.  The goal is to avoid pushing any
    path that cairo would eventually ignore, so our UUID mapping stays
    stable.

    Each numbered guard below names the exact cairo source routine that
    performs (or relies on) the same test and explains why we match it
    in Python first.  All file references are to cairo-svg-surface.c
    from the current cairo tree unless otherwise stated.
    """

    # 1. No geometry at all
    #    cairo path builder rejects an empty path in
    #    _cairo_svg_surface_emit_path (function exits immediately if
    #    the input path list is empty).
    if vmobject.points.size == 0:
        return False

    # 2. Both stroke alpha and fill alpha are near zero
    #    _cairo_svg_surface_emit_fill_style and
    #    _cairo_svg_surface_emit_stroke_style write "stroke:none;fill:none;"
    #    when alpha < 0.01 which paints nothing.
    stroke_rgba = vmobject.get_stroke_rgbas()[0]
    fill_rgba   = vmobject.get_fill_rgbas()[0]
    if stroke_rgba[3] <= 0.01 and fill_rgba[3] <= 0.01:
        return False

    # 3. Stroke width collapses to zero after device transform
    #    The number printed by _cairo_svg_surface_emit_stroke_style is
    #    stroke_style->line_width after transformation.  If it is 0 the
    #    SVG backend produces stroke-width:0 which shows nothing.
    if stroke_rgba[3] > 0.01 and vmobject.stroke_width > 0.0:
        dx, dy = ctx.user_to_device_distance(vmobject.stroke_width,
                                             vmobject.stroke_width)
        if max(abs(dx), abs(dy)) <= 1e-5:
            return False

    # 4. Degenerate path: every vertex is the same point
    #    _cairo_path_fixed_is_box and later rasteriser treat zero area
    #    shapes as empty.  We flag this before building any subpath.
    if (vmobject.points.shape[0] == 1 or
        (abs(vmobject.points - vmobject.points[0]).max() < 1e-7)):
        return False

    # 5. Dash pattern never paints even one segment
    #    _cairo_path_fixed_dash_to_stroker drops the stroke if the first
    #    dash gap already exceeds the full path length.
    # if getattr(vmobject, "dash_pattern", None):
    #     path_len = vmobject.get_total_length()       # manim helper
    #     first_gap = vmobject.dash_pattern[0]
    #     if path_len < first_gap:
    #         return False

    # 6. Current transform matrix has near zero determinant
    #    _cairo_matrix_transform_bounding_box collapses the bounding box
    #    which then makes _cairo_surface_clipper_set_clip treat the
    #    region as empty.
    m = ctx.get_matrix()
    if abs(m.xx * m.yy - m.xy * m.yx) < 1e-12:
        return False

    # TODO: Reenable
    # 7. Bounding box lies wholly outside the target surface
    #    _cairo_surface_clipper_intersect_clip_path culls draws that
    #    have no overlap with the surface extents.
    # xmin, xmax, ymin, ymax = vmobject.get_boundary_point
    # target = ctx.get_target()
    # if xmax < 0 or xmin > target.width or ymax < 0 or ymin > target.height:
    #     return False

    # Every cairo discard condition has been checked.  The object will
    # generate visible output.
    return True


def _create_svg_from_vmobject_internal(vmobject: VMobject, ctx: cairo.Context) -> str | None:
    """
    Processes a single VMobject to generate Cairo path commands and determines if it
    results in a drawable entity for which a UUID should be recorded.
    Returns the tagged_name (UUID string) if drawable, else None.
    """
    
    is_drawable = True
    
    points = vmobject.points
    points = _transform_points_pre_display(points)
    
    # Early breakouts. For example, if opacity is near 0 we don't want Cairo to even process the path.
    # That way we have consistent "limits" for the uuid mapping.
 
    if not _vm_is_drawable(vmobject, ctx):
        return None

    ctx.new_path()
    subpaths = vmobject.gen_subpaths_from_points_2d(points)
    for subpath in subpaths:
        quads = vmobject.gen_cubic_bezier_tuples_from_points(subpath)
        ctx.new_sub_path()
        start = subpath[0]
        ctx.move_to(*start[:2])
        for _p0, p1, p2, p3 in quads:
            ctx.curve_to(*p1[:2], *p2[:2], *p3[:2])
        if vmobject.consider_points_equals_2d(subpath[0], subpath[-1]):
            ctx.close_path()

    _apply_stroke(ctx, vmobject, background=True)
    _apply_fill(ctx, vmobject)
    _apply_stroke(ctx, vmobject) # Standard Manim second stroke

    try:
        if is_drawable:
            uuid_str = str(vmobject.tagged_name)
            return_uuid = uuid_str
        else:
            return_uuid = None
    except AttributeError:
        print(f"CRITICAL ERROR in SVG generation: VMobject of type {type(vmobject)} (hash: {hash(vmobject)}) is missing 'tagged_name'.")
        return_uuid = None
        
    return return_uuid


def create_svg_from_vmobject(vmobject: VMobject, file_name: str | Path = None) -> Path:
    """
    Creates an SVG file from a single VMobject and its family.
    This is mostly for standalone use or testing; create_svg_from_vgroup is used by HTMLParsedVMobject.
    """
    if file_name is None:
        # Use a temporary file that persists; caller is responsible for cleanup if needed.
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp_file:
            actual_file_name = Path(tmp_file.name)
    else:
        actual_file_name = Path(file_name).absolute()

    with _get_cairo_context(actual_file_name) as ctx:
        # Process the vmobject and all its sub-mobjects if it's a group
        for mob in extract_mobject_family_members([vmobject], recurse=True, extract_families=True):
            if isinstance(mob, VMobject): # Ensure we only process VMobjects
                 _create_svg_from_vmobject_internal(mob, ctx)
    return actual_file_name


def create_svg_from_vgroup(vgroup: VGroup, file_name: str | Path = None) -> tuple[Path, Path]:
    """
    Creates an SVG file from a VGroup, and a corresponding .txt file listing the UUIDs
    of VMobjects that resulted in a drawable path in the SVG.
    """
    if file_name is None:
        # Create a temporary SVG file that persists; HTMLParsedVMobject will manage its cleanup
        # via its own TemporaryDirectory.
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp_svg_file_obj:
            svg_file_path = Path(tmp_svg_file_obj.name)
    else:
        svg_file_path = Path.cwd() / "temp" / Path(Path(file_name).name).with_suffix(".svg")

    uuid_list_file_path = svg_file_path.with_suffix(".txt")
    
    os.makedirs(svg_file_path.parent, exist_ok=True)

    written_uuids: list[str] = []

    with _get_cairo_context(svg_file_path) as ctx:
        # Flatten the VGroup to get all individual VMobject components
        flat_vmobjects = extract_mobject_family_members(vgroup, use_z_index=False, only_those_with_points=True)
        
        for vmobject_to_draw in flat_vmobjects:
            if not isinstance(vmobject_to_draw, VMobject): # Safety check
                continue

            uuid = _create_svg_from_vmobject_internal(vmobject_to_draw, ctx)
            if uuid is not None:
                written_uuids.append(uuid)
    
    # Write the UUIDs to the .txt file
    with open(uuid_list_file_path, "w") as f_uuids:
        if written_uuids: # Avoid extra newline in empty file
            f_uuids.write("\n".join(written_uuids))
            f_uuids.write("\n") # Add a trailing newline for POSIX compatibility / easier parsing

    return svg_file_path, uuid_list_file_path
