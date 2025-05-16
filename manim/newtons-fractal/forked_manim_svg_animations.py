"""
Refactored `forked_manim_svg_animations.py`  (May 2025)
======================================================

This version keeps the **public API** identical (e.g. `HTMLParsedVMobject` is
constructed and used in exactly the same way) **but restructures the internals**
so that it is now trivial to add optimisation / transformation passes to the
JavaScript that drives the final SVG animation.

*  The heavy-weight logic that *builds* the list-of-JS-statements for each frame
   is now isolated in the private class `_JSFrameBuilder`.
*  A minimal plugin system (`register_optimizer`) lets you inject any number of
   post-processing passes.  Each pass receives the complete list of frames as
   *mutable* Python lists and may rewrite them in place or return a new value.
*  The default pipeline contains only the identity pass, so the generated
   output is byte-for-byte identical to the previous behaviour.

Example optimisation plug-in  (place **anywhere** after the imports, or in a
separate module that you `import` before you call `finish()`):

from forked_manim_svg_animations import register_optimizer

@register_optimizer
def collapse_fill_opacity(frames, context):
    Roll identical `setAttribute('fill-opacity', …)` calls into a loop
    for cmds in frames:
        # toy demo - merge 3 or more consecutive identical ops on path_pool
        i = 0
        while i < len(cmds):
            if (
                "setAttribute('fill-opacity'" in cmds[i]
                and i + 2 < len(cmds)
                and cmds[i][: cmds[i].find("='fill-opacity'")] == cmds[i + 1][
                    : cmds[i + 1].find("='fill-opacity'")
                ]
                and cmds[i][: cmds[i].find("='fill-opacity'")] == cmds[i + 2][
                    : cmds[i + 2].find("='fill-opacity'")
                ]
            ):
                # Found at least three identical calls - rewrite…
                lhs = cmds[i].split(".setAttribute")[0]
                cmds[i : i + 3] = [f"{lhs}.forEach(e => e.setAttribute('fill-opacity', '0.27'));"]
            i += 1
    return frames

The rest of the file is a mostly mechanical refactor of the original code - the
algorithms are unchanged, but the *layout* is far more readable.
"""

from __future__ import annotations

import os
import re
import math
import tempfile
from pathlib import Path
from typing import Callable, List, Dict, Any, Iterable, Tuple
from dataclasses import dataclass, field


import numpy as np
import xml.etree.ElementTree as ET
from svgpathtools import parse_path
from manim import *

# Local sibling modules (no public changes)
from manim_mobject_svg import *  # noqa: F401, pylint: disable=wildcard-import
from forked_svg import create_svg_from_vgroup


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>{title}</title>
</head>
<body style=\"background-color:black;\">
    <svg id=\"{svg_id}\" width=\"{width}\" viewBox=\"0 0 {w_px} {h_px}\" style=\"background-color:{bg};\"></svg>
    {extra_body}
    <script src=\"{js_file}\"></script>
</body>
</html>"""

SIMPLE_HTML_TEMPLATE = """<div>
    <svg id=\"{svg_id}\" width=\"{width}\" viewBox=\"0 0 {w_px} {h_px}\" style=\"background-color:{bg};\"></svg>
</div>"""

JS_WRAPPER = """let rendered = false;
let playing  = false;
const {svg_var} = document.getElementById(\"{svg_id}\");
{element_declarations}
{frames_array}

// Kick-off entry point (called from HTML or user code)
function render{scene_name}() {{
    if (playing) return;          // prevent overlapping playbacks
    playing  = true;
    rendered = false;
    let i = 0;
    function step() {{
        if (i < frames.length) {{
            frames[i++]();        // run one frame's updater
            requestAnimationFrame(step);
        }} else {{
            playing  = false;
            rendered = true;
        }}
    }}
    requestAnimationFrame(step);
}}
"""

# -----------------------------------------------------------------------------
#                 Optimiser framework
# -----------------------------------------------------------------------------

Optimizer = Callable[[List[List[str]], Dict[str, Any]], List[List[str]]]

# Registry filled via @register_optimizer decorator
_OPTIMISERS: List[Optimizer] = []

def register_optimizer(func: Optimizer) -> Optimizer:  # noqa: D401
    """Decorator register *func* as an optimisation pass.

    The function must take `(frames, context)` and *either* modify `frames` in
    place *or* return a **new** list of frames (the return value will be used
    if it is not `None`).  `context` is a **plain dict** with metadata that may
    be useful to the optimiser (pool sizes, svg_id, ...). The contents are small
    on purpose extend as you see fit.
    """
    _OPTIMISERS.append(func)
    return func

# Identity pass so that, even with no user supplied optimisers, we keep the
# behaviour 100 % identical.
@register_optimizer
def _noop(frames: List[List[str]], context: Dict[str, Any]) -> List[List[str]]:  # noqa: D401
    return frames


# -----------------------------------------------------------------------------
#                 Internal data helpers / small utilities
# -----------------------------------------------------------------------------

@staticmethod
def _round_value(attr: str, value: str, precision: int = 2) -> str:  # lifted unchanged
    if attr == "d":
        def repl(m):
            try:
                return str(round(float(m.group()), precision))
            except ValueError:
                return m.group()
        return re.sub(r"[+-]?\d*\.?\d+(?:[eE][+-]?\d+)?", repl, value)
    if attr in {"cx", "cy", "r", "stroke-width", "opacity",
                "fill-opacity", "stroke-opacity", "stroke-miterlimit"}:
        try:
            num = float(value)
            return str(round(num, precision))
        except ValueError:
            return value
    if value.startswith(("rgb(", "rgba(")):
        head = "rgba(" if value.startswith("rgba") else "rgb("
        nums = [n.strip() for n in value[len(head):-1].split(",")]
        out: List[str] = []
        for i, n in enumerate(nums):
            if n.endswith("%"):
                out.append(f"{round(float(n[:-1]), precision)}%")
            else:
                out.append(str(round(float(n), precision if head == "rgba(" and i == 3 else 0)))
        return head + ", ".join(out) + ")"
    return value

@staticmethod
def _detect_circle(path_d: str, tol: float = 1e-2):  # unchanged helper
    try:
        path = parse_path(path_d)
    except Exception:  # pragma: no cover – svgpathtools throws many…
        return None
    if len(path) == 0 or not (path.iscontinuous() and path.isclosed()):
        return None
    samples = {seg.start for seg in path} | {seg.end for seg in path} | {seg.point(0.5) for seg in path}
    if len(samples) < 3:
        return None
    pts = np.array([(p.real, p.imag) for p in samples])
    X, Y = pts[:, 0], pts[:, 1]
    M = np.vstack([X, Y, np.ones(len(pts))]).T
    b = -(X ** 2 + Y ** 2)
    try:
        (A, B, C), *_ = np.linalg.lstsq(M, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cx, cy = -A / 2, -B / 2
    r2 = (A ** 2 + B ** 2) / 4 - C
    if r2 <= max(tol ** 2 * 0.01, 1e-9):
        return None
    r = math.sqrt(r2)
    if any(abs(math.hypot(p.real - cx, p.imag - cy) - r) > tol for p in samples):
        return None
    return cx, cy, r


@dataclass
class _SceneFrameMeta:  # slim container for per-frame scene data
    bg: str
    viewbox: List[str] | None


@dataclass
class _PathElementState:  # mutable dict behind the scenes but with a fixed type
    attrs: Dict[str, str] = field(default_factory=dict)
    display: str | None = None  # '', 'none', …


# -----------------------------------------------------------------------------
#                 3 — Frame builder (unchanged *logic*, nicer *code*)
# -----------------------------------------------------------------------------

class _JSFrameBuilder:
    """Translate the collected raw data → JS-statement lists.

    This still follows *exactly* the previous algorithm (pooling, diffing …)
    but lives in its own self-contained helper so that `HTMLParsedVMobject`
    stays approachable.
    """

    def __init__(
        self,
        tracked_objects: Dict[str, List[Dict[str, str] | None]],
        scene_frames: List[_SceneFrameMeta],
        svg_var: str,
        scene_name: str,
    ) -> None:
        self.tracked_objects = tracked_objects
        self.scene_frames = scene_frames
        self.svg_var = svg_var
        self.scene_name = scene_name
        self.all_uuids = list(tracked_objects.keys())
        self.num_frames = len(scene_frames)

        # These are filled by _analyse_pool_sizes() ↓
        self.max_paths = 0
        self.max_circles = 0

    # utils

    def _analyse_pool_sizes(self) -> None:
        for i in range(self.num_frames):
            paths = circles = 0
            for uuid in self.all_uuids:
                if i < len(self.tracked_objects[uuid]):
                    obj_data = self.tracked_objects[uuid][i]
                    if obj_data:
                        if obj_data.get("_shape") == "circle":
                            circles += 1
                        else:
                            paths += 1
            self.max_paths = max(self.max_paths, paths)
            self.max_circles = max(self.max_circles, circles)

    def build_frames(self) -> Tuple[str, List[List[str]], Dict[str, Any]]:
        """Return `(element_declarations, frames, context)`.

        * `element_declarations` - crust that goes right after the `const svg` …
        * `frames`               - list[ frameCommands ]
        * `context`              - small dict handed to optimisers
        """
        self._analyse_pool_sizes()

        # Pre-allocate python-side state mirrors
        path_state: List[_PathElementState] = [ _PathElementState() for _ in range(self.max_paths) ]
        circ_state: List[_PathElementState] = [ _PathElementState() for _ in range(self.max_circles) ]

        scene_bg_state: str | None = None
        scene_viewbox_state: List[str] | None = None

        # --- element declarations (executed *once* in the JS wrapper) -------
        elem_decl_lines: List[str] = [
            "    const path_pool = [];",
            "    const circle_pool = [];",
        ]
        init_lines: List[str] = [
            "while (path_pool.length) { path_pool.pop(); }",
            "while (circle_pool.length) { circle_pool.pop(); }",
            f"{self.svg_var}.replaceChildren();",
        ]
        for i in range(self.max_paths):
            init_lines.extend([
                f"const p{i} = document.createElementNS('http://www.w3.org/2000/svg','path');",
                f"{self.svg_var}.appendChild(p{i});",
                f"path_pool.push(p{i});",
            ])
        for i in range(self.max_circles):
            init_lines.extend([
                f"const c{i} = document.createElementNS('http://www.w3.org/2000/svg','circle');",
                f"{self.svg_var}.appendChild(c{i});",
                f"circle_pool.push(c{i});",
            ])

        # per-frame command editing
        frames_js: List[List[str]] = []

        for frame_idx in range(self.num_frames):
            cmds: List[str] = []
            if frame_idx == 0:
                cmds.extend(init_lines)

            path_slot = circ_slot = 0
            active_this_frame: set[Tuple[str, int]] = set()

            for uuid in self.all_uuids:
                current_attrs = (
                    self.tracked_objects[uuid][frame_idx]
                    if frame_idx < len(self.tracked_objects[uuid])
                    else None
                )
                if not current_attrs:
                    continue

                shape = current_attrs.get("_shape", "path")
                if shape == "path":
                    js_elem, slot, state_list = f"path_pool[{path_slot}]", path_slot, path_state
                    path_slot += 1
                else:
                    js_elem, slot, state_list = f"circle_pool[{circ_slot}]", circ_slot, circ_state
                    circ_slot += 1
                active_this_frame.add((shape, slot))

                elem_state = state_list[slot]
                # Sync attrs
                set_now: Dict[str, str] = {}
                for k, v in current_attrs.items():
                    if k == "_shape":
                        continue
                    v_str = str(v)
                    set_now[k] = v_str
                    if elem_state.attrs.get(k) != v_str:
                        esc = v_str.replace("\\", "\\\\").replace("'", "\\'")
                        cmds.append(f"{js_elem}.setAttribute('{k}', '{esc}');")
                        elem_state.attrs[k] = v_str
                # Remove stale
                for stale in list(elem_state.attrs.keys()):
                    if stale not in set_now and stale != "style.display":
                        cmds.append(f"{js_elem}.removeAttribute('{stale}');")
                        del elem_state.attrs[stale]
                # Ensure visible
                if elem_state.display != "":
                    cmds.append(f"{js_elem}.style.display = '';")
                    elem_state.display = ""

            # Hide unused pool slots
            for i in range(self.max_paths):
                if ("path", i) not in active_this_frame and path_state[i].display != "none":
                    cmds.append(f"path_pool[{i}].style.display = 'none';")
                    path_state[i].display = "none"
            for i in range(self.max_circles):
                if ("circle", i) not in active_this_frame and circ_state[i].display != "none":
                    cmds.append(f"circle_pool[{i}].style.display = 'none';")
                    circ_state[i].display = "none"

            # Scene-level bits
            meta = self.scene_frames[frame_idx]
            if meta.bg != scene_bg_state:
                cmds.append(f"{self.svg_var}.style.backgroundColor='{meta.bg}';")
                scene_bg_state = meta.bg
            if meta.viewbox != scene_viewbox_state:
                if meta.viewbox:
                    vb_str = " ".join(map(str, meta.viewbox))
                    cmds.append(f"{self.svg_var}.setAttribute('viewBox','{vb_str}');")
                else:
                    cmds.append(f"{self.svg_var}.removeAttribute('viewBox');")
                scene_viewbox_state = meta.viewbox

            frames_js.append(cmds)

        # Build small optimisation context
        opt_context = {
            "svg_var": self.svg_var,
            "scene_name": self.scene_name,
            "max_paths": self.max_paths,
            "max_circles": self.max_circles,
        }
        return "\n".join(elem_decl_lines), frames_js, opt_context


# -----------------------------------------------------------------------------
#                       Public facade
# -----------------------------------------------------------------------------

class HTMLParsedVMobject:
    """Collects per-frame SVG snapshots from a Manim *VMobject* (or *VGroup*)."""

    def __init__(self, vmobject: VMobject, scene: Scene, *, width: str = "500px", basic_html: bool = False):
        self.vmobject = vmobject
        self.scene = scene
        self.width = width
        self.basic_html = basic_html

        self.basename = scene.__class__.__name__
        self.html_path = os.path.join("media", "svg_animations", self.basename + ".html")
        self.js_path = os.path.join("media", "svg_animations", self.basename + ".js")

        self.frame_index = 0
        self.tracked_objects: Dict[str, List[Dict[str, str] | None]] = {}
        self.scene_frames: List[_SceneFrameMeta] = []
        self.collecting = True

        self.orig_w = scene.camera.frame_width
        self.orig_h = scene.camera.frame_height

        self._write_html_shell()
        scene.add_updater(self._frame_updater)  # type: ignore[arg-type]

    def _write_html_shell(self):
        cam = self.scene.camera
        bg_rgba = color_to_int_rgba(cam.background_color, cam.background_opacity)
        bg_rgba[-1] /= 255
        bg_str = f"rgb({', '.join(map(str, bg_rgba))})"
        html_body = SIMPLE_HTML_TEMPLATE if self.basic_html else HTML_TEMPLATE
        self.html_markup = html_body.format(
            title=self.basename,
            svg_id=self.basename,
            width=self.width,
            w_px=cam.pixel_width,
            h_px=cam.pixel_height,
            bg=bg_str,
            extra_body="",
            js_file=os.path.basename(self.js_path)
        )

    def _frame_updater(self, dt: float):
        """Called each render tick by Manim - serialize current VMobject to SVG."""
        if not self.collecting:
            return

        base_tmp_filename = f"{self.basename}_{self.frame_index}"
        with tempfile.TemporaryDirectory() as tmpdir:
            svg_filepath, uuid_list_filepath = create_svg_from_vgroup(self.vmobject, str(base_tmp_filename))

            uuids_from_file: list[str] = []
            if os.path.exists(uuid_list_filepath):
                with open(uuid_list_filepath, 'r') as f_uuid_list:
                    uuids_from_file = [line.strip() for line in f_uuid_list if line.strip()]
            else:
                print(f"ERROR: UUID list file {uuid_list_filepath} was not generated for frame {self.frame_index}. No SVG data can be reliably mapped for this frame.")

            temp_parsed_svg_data_for_paths: list[dict] = [] # Holds parsed data for paths found in SVG
            svg_paths_found_count = 0

            try:
                tree = ET.parse(svg_filepath)
                root = tree.getroot()
                ns_uri = "http://www.w3.org/2000/svg"
                if root.tag.startswith("{"):
                    end_brace_index = root.tag.find('}')
                    if end_brace_index != -1:
                        ns_uri = root.tag[1:end_brace_index]
                ns = {"svg": ns_uri}
                svg_path_elements = root.findall(".//svg:path", ns)
                svg_paths_found_count = len(svg_path_elements)

                for path_element in svg_path_elements:
                    raw_attr = dict(path_element.attrib)
                    entry = {}
                    path_def = str(raw_attr.get("d", ""))
                    circle_params = _detect_circle(path_def)
                    if circle_params:
                        cx, cy, r = circle_params
                        entry["_shape"] = "circle"
                        entry["cx"] = _round_value("cx", str(cx))
                        entry["cy"] = _round_value("cy", str(cy))
                        entry["r"]  = _round_value("r",  str(r))
                    else:
                        entry["_shape"] = "path"
                        entry["d"] = _round_value("d", path_def)
                    for k, v in raw_attr.items():
                        if k == "d":
                            if entry["_shape"] == "path" and "d" not in entry:
                                entry["d"] = _round_value("d", path_def)
                            continue
                        entry[k] = _round_value(k, str(v))
                    temp_parsed_svg_data_for_paths.append(entry)

            except (ET.ParseError, FileNotFoundError) as e:
                print(f"Error parsing SVG {svg_filepath} for frame {self.frame_index}: {e}. No SVG data will be used.")
                # temp_parsed_svg_data_for_paths remains empty, svg_paths_found_count is 0 or from len before error
            
            # Core data mapping logic:
            # uuids_from_file is the source of truth for *rendered* elements this frame.
            mapped_uuids_in_current_frame = set()

            if uuids_from_file and len(uuids_from_file) == svg_paths_found_count:
                print(f"Frame {self.frame_index}: Found {len(uuids_from_file)} UUIDs in file, {svg_paths_found_count} paths in SVG")
                for i, uuid_str in enumerate(uuids_from_file):
                    if uuid_str not in self.tracked_objects:
                        # New UUID encountered via .txt file, ensure it's initialized for all previous frames with None
                        self.tracked_objects[uuid_str] = [None] * self.frame_index
                    elif len(self.tracked_objects[uuid_str]) < self.frame_index:
                        # Existing UUID, but its history is shorter than expected (e.g. reappeared after absence)
                        self.tracked_objects[uuid_str].extend([None] * (self.frame_index - len(self.tracked_objects[uuid_str])))
                    
                    # Append current frame's data
                    self.tracked_objects[uuid_str].append(temp_parsed_svg_data_for_paths[i])
                    mapped_uuids_in_current_frame.add(uuid_str)
            elif uuids_from_file or svg_paths_found_count > 0: # Mismatch case
                print(f"Frame {self.frame_index}: WARNING - Mismatch between UUIDs from file ({len(uuids_from_file)}) and SVG paths found ({svg_paths_found_count}). Attempting to copy data from previous frame for existing tracked objects.")
                if self.frame_index > 0:
                    for uuid_str_to_copy in self.tracked_objects.keys():
                        # Ensure this UUID was present up to the previous frame.
                        # Its list should have length self.frame_index (elements for frames 0 to frame_index-1)
                        if len(self.tracked_objects[uuid_str_to_copy]) == self.frame_index:
                            prev_data = self.tracked_objects[uuid_str_to_copy][self.frame_index - 1]
                            self.tracked_objects[uuid_str_to_copy].append(prev_data) # Copy previous data for current frame
                            # Mark as handled for this frame, regardless of whether prev_data was None or actual data.
                            # This prevents the later block from appending another None if prev_data was None
                            # and correctly reflects that this UUID's state for the current frame has been determined.
                            mapped_uuids_in_current_frame.add(uuid_str_to_copy)
                else: # self.frame_index == 0
                    print(f"Frame {self.frame_index}: Mismatch on first frame (frame_index 0). Cannot copy previous data. Objects will be handled by subsequent logic.")
            # For any UUID tracked previously (or part of current family) but not mapped in *this* frame, append None.
            # Also ensures any new UUIDs from current family (if not in .txt) are initialized correctly.
            current_family_uuids = {getattr(obj, "tagged_name", f"fallback_frameupdater_{i}") 
                                    for i, obj in enumerate(self.vmobject.get_family())}
            
            all_potentially_relevant_uuids = set(self.tracked_objects.keys()).union(current_family_uuids)

            for uuid_str in all_potentially_relevant_uuids:
                if uuid_str not in self.tracked_objects: # New UUID from family, not in .txt, not seen before
                    self.tracked_objects[uuid_str] = [None] * (self.frame_index + 1) # Init with None for all frames up to current
                elif uuid_str not in mapped_uuids_in_current_frame:
                    # Was tracked, or in family, but not in current frame's successful mapping.
                    # Ensure list is padded to current_frame_index -1, then append None for current frame.
                    if len(self.tracked_objects[uuid_str]) < self.frame_index:
                        self.tracked_objects[uuid_str].extend([None] * (self.frame_index - len(self.tracked_objects[uuid_str])))
                    if len(self.tracked_objects[uuid_str]) == self.frame_index: # Ready for current frame data
                         self.tracked_objects[uuid_str].append(None)

        # Scene-wide metadata
        bg_rgba = color_to_int_rgba(self.scene.camera.background_color,
                                    self.scene.camera.background_opacity)
        bg_rgba[-1] /= 255
        bg_str  = f"rgb({', '.join(map(str, bg_rgba))})"

        viewbox = None
        if isinstance(self.scene, MovingCameraScene):
            cam   = self.scene.camera
            pw    = cam.pixel_width  * cam.frame_width  / self.orig_w
            ph    = cam.pixel_height * cam.frame_height / self.orig_h
            top_l = cam.frame.get_corner(UL) * cam.pixel_width / self.orig_w
            center = top_l + cam.pixel_width / 2 * RIGHT + cam.pixel_height / 2 * DOWN
            center[1] = -center[1] # SVG Y is inverted
            viewbox = list(map(str, [*center[:2], pw, ph]))

        self.scene_frames.append(_SceneFrameMeta(
            bg=bg_str,
            viewbox=viewbox
        ))
        self.frame_index += 1

    def finish(self):
        """Stop collection, run compilation pipeline, write .js / .html."""
        # Freeze data collection
        if self.collecting:
            self.scene.remove_updater(self._frame_updater)  # type: ignore[arg-type]
            self.collecting = False
        num_frames = self.frame_index

        # Early out if nothing happened at all
        if num_frames == 0 or not self.tracked_objects:
            os.makedirs(os.path.dirname(self.js_path), exist_ok=True)
            with open(self.js_path, "w", encoding="utf-8") as f_js:
                element_decls = "    const path_pool = [];\n    const circle_pool = [];"
                f_js.write(
                    JS_WRAPPER.format(
                        svg_var=self.basename.lower(),
                        svg_id=self.basename,
                        element_declarations=element_decls,
                        frames_array="const frames = [];",
                        scene_name=self.basename,
                    )
                )
            with open(self.html_path, "w", encoding="utf-8") as f_html:
                f_html.write(self.html_markup)
            return

        # Build per-frame JS arrays 
        builder = _JSFrameBuilder(
            tracked_objects=self.tracked_objects,
            scene_frames=self.scene_frames,
            svg_var=self.basename.lower(),
            scene_name=self.basename,
        )
        element_decls, frames_js, opt_ctx = builder.build_frames()

        # Optimiser pipeline
        for optim in _OPTIMISERS:
            maybe_new = optim(frames_js, opt_ctx) or frames_js
            # ensure *exact* same nested list structure if pass returns None
            frames_js = maybe_new

        # Serialise JS / HTML
        frame_blocks: List[str] = []
        for idx, cmds in enumerate(frames_js):
            indented = "\n        ".join(cmds)
            frame_blocks.append(f"    () => {{\n        // Frame {idx}\n        {indented}\n    }}")
        frames_array_js = "const frames = [\n" + ",\n".join(frame_blocks) + "\n];"

        js_output = JS_WRAPPER.format(
            svg_var=self.basename.lower(),
            svg_id=self.basename,
            element_declarations=element_decls,
            frames_array=frames_array_js,
            scene_name=self.basename,
        )

        os.makedirs(os.path.dirname(self.js_path), exist_ok=True)
        with open(self.js_path, "w", encoding="utf-8") as f_js:
            f_js.write(js_output)
        with open(self.html_path, "w", encoding="utf-8") as f_html:
            f_html.write(self.html_markup)

