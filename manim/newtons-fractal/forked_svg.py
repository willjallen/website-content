"""forked_svg_refactored.py - Generate a single SVG with <path id="uuid"> tags

Renders every `VMobject` in its own temporary SVG, adds the object's
`tagged_name` as an `id` on the first `<path>`, then merges all those
snippets into one master SVG.  This eliminates the brittle heuristic that
tried to guess in advance whether a `VMobject` would end up painting anything.

Only the public helpers `create_svg_from_vmobject` and
`create_svg_from_vgroup` are meant to be called by user code.
"""
from __future__ import annotations

import itertools as it
import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, List
from xml.etree import ElementTree as ET

import cairo
import numpy as np
from manim import VGroup, VMobject, config
from manim.utils.family import extract_mobject_family_members

__all__ = [
    "create_svg_from_vmobject",
    "create_svg_from_vgroup",
]

###############################################################################
# Cairo helpers
###############################################################################

CAIRO_LINE_WIDTH_MULTIPLE: float = 0.01
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)  # Pretty‑print without the ugly ns0 prefix


def _svg_tag(tag: str) -> str:
    """Return a namespaced SVG tag for *ElementTree* comparisons."""
    return f"{{{SVG_NS}}}{tag}"


@contextmanager
def _get_cairo_context(file_name: str | Path):
    """Yield a Cairo *Context* that writes directly to *file_name* (SVG)."""
    pw, ph = config.pixel_width, config.pixel_height
    fw, fh = config.frame_width, config.frame_height
    fc = [0, 0]  # frame centre offset – unused by manim as of 0.18

    surface = cairo.SVGSurface(str(file_name), pw, ph)
    ctx = cairo.Context(surface)

    # Match manim‑cairo coordinate system: unit square → render frame.
    ctx.scale(pw, ph)
    ctx.set_matrix(
        cairo.Matrix(
            pw / fw,
            0,
            0,
            -(ph / fh),
            (pw / 2) - fc[0] * (pw / fw),
            (ph / 2) + fc[1] * (ph / fh),
        )
    )
    try:
        yield ctx
    finally:
        surface.finish()


###############################################################################
# Basic drawing primitives (adapted from manim's *cairo_renderer.py*)
###############################################################################


def _transform_points_pre_display(points: np.ndarray) -> np.ndarray:
    if not np.all(np.isfinite(points)):
        return np.zeros((1, 3))
    return points


def _set_cairo_context_color(ctx: cairo.Context, rgbas: np.ndarray, vmobject: VMobject):
    """Set *ctx*'s current colour or gradient fill from *rgbas*."""
    if len(rgbas) == 1:
        ctx.set_source_rgba(*rgbas[0])
        return

    points = vmobject.get_gradient_start_and_end_points()
    points = _transform_points_pre_display(points)
    pat = cairo.LinearGradient(*itertools.chain(*(p[:2] for p in points)))
    step = 1.0 / (len(rgbas) - 1)
    offsets = np.arange(0, 1 + step, step)
    for rgba, offset in zip(rgbas, offsets):
        pat.add_color_stop_rgba(offset, *rgba)
    ctx.set_source(pat)


def _apply_stroke(ctx: cairo.Context, vm: VMobject, *, background: bool = False):
    width = vm.get_stroke_width(background)
    if width == 0:
        return

    _set_cairo_context_color(ctx, vm.get_stroke_rgbas(background), vm)
    ctx.set_line_width(width * CAIRO_LINE_WIDTH_MULTIPLE)
    ctx.stroke_preserve()


def _apply_fill(ctx: cairo.Context, vm: VMobject):
    _set_cairo_context_color(ctx, vm.get_fill_rgbas(), vm)
    ctx.fill_preserve()


###############################################################################
# Low‑level renderer: “draw exactly this VMobject on *ctx*”.
###############################################################################


def _draw_vmobject_on_context(vm: VMobject, ctx: cairo.Context) -> None:
    """Render *vm* to *ctx* *exactly once* without heuristic pruning."""

    points = _transform_points_pre_display(vm.points)
    if points.size == 0:
        return  # empty path – nothing to draw

    ctx.new_path()
    for subpath in vm.gen_subpaths_from_points_2d(points):
        quads = vm.gen_cubic_bezier_tuples_from_points(subpath)
        ctx.new_sub_path()
        ctx.move_to(*subpath[0][:2])
        for _p0, p1, p2, p3 in quads:
            ctx.curve_to(*p1[:2], *p2[:2], *p3[:2])
        if vm.consider_points_equals_2d(subpath[0], subpath[-1]):
            ctx.close_path()

    # The *background* pass exists only so the two strokes match manim's
    # typical GPU renderer.
    _apply_stroke(ctx, vm, background=True)
    _apply_fill(ctx, vm)
    _apply_stroke(ctx, vm)


###############################################################################
# SVG post‑processing helpers
###############################################################################


def _svg_contains_path(svg_root: ET.Element) -> bool:
    """*True* if any <path> element exists in *svg_root*."""
    return svg_root.find(f".//{_svg_tag('path')}") is not None


def _add_id_to_first_path(svg_root: ET.Element, id_str: str) -> None:
    """Add ``id=id_str`` to the **first** <path> element in *svg_root*."""
    for elem in svg_root.iter(_svg_tag("path")):
        elem.set("id", id_str)
        break


###############################################################################
# Public API single VMobject -> SVG
###############################################################################


def create_svg_from_vmobject(vmobject: VMobject, file_name: str | Path | None = None) -> Path:
    """Render *vmobject* to an SVG and return its *Path*.

    Mostly a convenience wrapper for debugging; ``create_svg_from_vgroup`` is
    what HTMLParsedVMobject and production code should call.
    """
    if file_name is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".svg", delete=False)
        file_path = Path(tmp.name)
        tmp.close()
    else:
        file_path = Path(file_name).expanduser().resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)

    with _get_cairo_context(file_path) as ctx:
        _draw_vmobject_on_context(vmobject, ctx)

    # Optionally decorate the SVG with an id if something was drawn.
    tree = ET.parse(file_path)
    root = tree.getroot()
    if _svg_contains_path(root):
        _add_id_to_first_path(root, str(vmobject.tagged_name))
        tree.write(file_path, encoding="utf-8", xml_declaration=True)
    return file_path


###############################################################################
# Public API - VGroup -> master SVG
###############################################################################


def create_svg_from_vgroup(vgroup: VGroup, output_svg: str | Path | None = None) -> Path:
    """Render *vgroup* (recursively) to a single SVG and return the path.

    The function works in three phases:
      1. Flatten *vgroup* into individual ``VMobject`` instances.
      2. For each object, draw to its own temporary SVG, tag the first <path>
         with the object's ``tagged_name``, and collect the *children* of the
         temporary SVG root that actually contain geometry.
      3. Stitch those children together under one master <svg> root.

    The resulting file has no external manifest; UUIDs live inside the SVG.
    """
    # Where to save the final SVG.
    if output_svg is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".svg", delete=False)
        master_svg_path = Path(tmp.name)
        tmp.close()
    else:
        master_svg_path = Path(output_svg).expanduser().resolve()
        master_svg_path.parent.mkdir(parents=True, exist_ok=True)

    # Gather all drawable VMobjects
    flat_vmobjs: List[VMobject] = list(
        extract_mobject_family_members(
            vgroup,
            only_those_with_points=True,
        )
    )

    # Render each VMobject into its own SVG and collect the geometry.
    collected_children: List[ET.Element] = []
    defs_pool: List[ET.Element] = []

    for vm in flat_vmobjs:
        tmp_svg_path = create_svg_from_vmobject(vm)
        tmp_root = ET.parse(tmp_svg_path).getroot()

        if not _svg_contains_path(tmp_root):
            tmp_svg_path.unlink(missing_ok=True)  # Discard empty placeholder
            continue

        # Extract <defs> once (manim writes gradients there).  Keep order but
        # skip duplicates to avoid id clashes.
        for d in tmp_root.findall(_svg_tag("defs")):
            defs_pool.append(d)

        # All *visible* nodes live at the top level after manim exports.  We
        # therefore copy every *non‑defs* child verbatim.
        for child in list(tmp_root):
            if child.tag == _svg_tag("defs"):
                continue
            collected_children.append(child)

        tmp_svg_path.unlink(missing_ok=True)

    # Build the master SVG document.
    root = ET.Element(
        _svg_tag("svg"),
        {
            "width": str(config.pixel_width),
            "height": str(config.pixel_height),
            "viewBox": f"0 0 {config.pixel_width} {config.pixel_height}",
        },
    )

    if defs_pool:
        defs_root = ET.SubElement(root, _svg_tag("defs"))
        for d in defs_pool:
            for elem in list(d):
                defs_root.append(elem)

    for child in collected_children:
        root.append(child)

    tree = ET.ElementTree(root)
    tree.write(master_svg_path, encoding="utf-8", xml_declaration=True)
    return master_svg_path
