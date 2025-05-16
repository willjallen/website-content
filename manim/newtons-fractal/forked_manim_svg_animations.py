"""
Refactored `forked_manim_svg_animations.py`  (May 2025)
======================================================

This version keeps the **public API** identical (e.g. `HTMLParsedVMobject` is
constructed and used in exactly the same way) **but restructures the internals**
so that it is now trivial to add optimization / transformation passes to the
JavaScript that drives the final SVG animation.

*  The heavy-weight logic that *builds* the list-of-JS-statements for each frame
   is now isolated in the private class `_JSFrameBuilder`.
*  A minimal plugin system (`register_optimizer`) lets you inject any number of
   post-processing passes.  Each pass receives the complete list of frames as
   *mutable* Python lists and may rewrite them in place or return a new value.
*  The default pipeline contains only the identity pass, so the generated
   output is byte-for-byte identical to the previous behavior.

Example optimization plug-in  (place **anywhere** after the imports, or in a
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

from copy import copy, deepcopy
from multiprocessing import Process
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

import cloudpickle  # for serializing lambda-containing VMobjects across processes


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
let TARGET_DT = 16;   // ms between logical frames

function render{scene_name}() {{
    if (playing) return;          // prevent overlapping playbacks
    playing  = true;
    rendered = false;

    let i = 0;
    let lastTime = performance.now();

    function step(now) {{
        // Only advance when at least TARGET_DT ms have elapsed
        if (now - lastTime >= TARGET_DT) {{
            lastTime = now;

            if (i < frames.length) {{
                frames[i++]();    // run one frame's updater
            }} else {{
                playing  = false;
                rendered = true;
                return;          // stop when finished
            }}
        }}
        requestAnimationFrame(step);   // keep the loop alive
    }}

    requestAnimationFrame(step);
}}
"""

# -----------------------------------------------------------------------------
#                 Optimizer framework
# -----------------------------------------------------------------------------

Optimizer = Callable[[List[List[str]], Dict[str, Any]], List[List[str]]]

# Registry filled via @register_optimizer decorator
_OPTIMIZERS: List[Optimizer] = []

def register_optimizer(func: Optimizer) -> Optimizer:  # noqa: D401
    """Decorator register *func* as an optimization pass.

    The function must take `(frames, context)` and *either* modify `frames` in
    place *or* return a **new** list of frames (the return value will be used
    if it is not `None`).  `context` is a **plain dict** with metadata that may
    be useful to the optimizer (pool sizes, svg_id, ...). The contents are small
    on purpose extend as you see fit.
    """
    _OPTIMIZERS.append(func)
    return func

# Identity pass so that, even with no user supplied optimizers, we keep the
# behavior 100 % identical.
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
    except Exception:
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
class _PathElementState:  # mutable dict behind the scenes but with a fixed type
    attrs: Dict[str, str] = field(default_factory=dict)
    display: str | None = None  # '', 'none', ...


# -----------------------------------------------------------------------------
#                 Frame builder
# -----------------------------------------------------------------------------

class _JSFrameBuilder:
    """
    Translate the collected raw data -> JS-statement lists.
    """

    def __init__(
        self,
        tracked_objects: Dict[str, List[Dict[str, str] | None]],
        scene_frames: List[_SceneFrameMeta],
        svg_var: str,
        scene_name: str,
    ) -> None:
        # {uuid: [frame_0_data, frame_1_data, ...]}, frame data is None for frames that don't have this object
        self.tracked_objects = tracked_objects
        # {frame_0_meta, frame_1_meta, ...}
        self.scene_frames = scene_frames
        self.svg_var = svg_var
        self.scene_name = scene_name
        self.all_uuids = list(tracked_objects.keys())
        self.num_frames = len(scene_frames)

        # These are filled by _analyze_pool_sizes()
        self.max_paths = 0
        self.max_circles = 0

    # utils

    def _analyze_pool_sizes(self) -> None:
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
        * `context`              - small dict handed to optimizers
        """
        self._analyze_pool_sizes()

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

        # uuid pool leases:
        # each uuid is leased to a slot in the path_pool or circle_pool *for the contiguous range(s) of frames* where it is present
        # when the object disappears, the slot becomes free and can be reused by another object
        # this prevents shuffling around pool slots within an active range while still maximizing pool reuse overall
        
        # Dynamic lease state that will be updated as we iterate over frames
        path_slot_map: Dict[str, int] = {}
        circle_slot_map: Dict[str, int] = {}
        # Pools of free slot indices (pre-filled with the full capacity)
        free_path_slots: List[int] = list(range(self.max_paths))
        free_circle_slots: List[int] = list(range(self.max_circles))

        # per-frame command editing
        frames_js: List[List[str]] = []

        for frame_idx in range(self.num_frames):
            cmds: List[str] = []
            if frame_idx == 0:
                cmds.extend(init_lines)

            # Track which slots are actively used in this frame
            path_used_this_frame: set[int] = set()
            circle_used_this_frame: set[int] = set()

            # Helper to release a slot once an object disappears
            def _release_slot(uuid: str):
                if uuid in path_slot_map:
                    slot = path_slot_map.pop(uuid)
                    if slot not in free_path_slots:
                        free_path_slots.append(slot)
                elif uuid in circle_slot_map:
                    slot = circle_slot_map.pop(uuid)
                    if slot not in free_circle_slots:
                        free_circle_slots.append(slot)

            for uuid in self.all_uuids:
                current_attrs = (
                    self.tracked_objects[uuid][frame_idx]
                    if frame_idx < len(self.tracked_objects[uuid])
                    else None
                )

                if not current_attrs:
                    # Object is NOT present in this frame – release any previous lease
                    _release_slot(uuid)
                    continue

                shape = current_attrs.get("_shape", "path")

                # If the object changes type (path ↔ circle) release its previous slot first
                if shape == "path" and uuid in circle_slot_map:
                    _release_slot(uuid)
                elif shape == "circle" and uuid in path_slot_map:
                    _release_slot(uuid)

                if shape == "path":
                    # Ensure we have / obtain a slot for this uuid
                    if uuid not in path_slot_map:
                        # Lease a free slot for this new active range
                        if not free_path_slots:
                            raise RuntimeError("No free path slot available - max_paths mis-computed? ")
                        path_slot_map[uuid] = free_path_slots.pop(0)
                    slot = path_slot_map[uuid]
                    js_elem = f"path_pool[{slot}]"
                    state_list = path_state
                    path_used_this_frame.add(slot)
                else:  # circle
                    if uuid not in circle_slot_map:
                        if not free_circle_slots:
                            raise RuntimeError("No free circle slot available - max_circles mis-computed? ")
                        circle_slot_map[uuid] = free_circle_slots.pop(0)
                    slot = circle_slot_map[uuid]
                    js_elem = f"circle_pool[{slot}]"
                    state_list = circ_state
                    circle_used_this_frame.add(slot)

                elem_state = state_list[slot]
                # --- Attribute diff/patch -------------------------------------------------
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
                # Remove stale attributes
                for stale in list(elem_state.attrs.keys()):
                    if stale not in set_now and stale != "style.display":
                        cmds.append(f"{js_elem}.removeAttribute('{stale}');")
                        del elem_state.attrs[stale]
                # Ensure element is visible
                if elem_state.display != "":
                    cmds.append(f"{js_elem}.style.display = '';")
                    elem_state.display = ""

            # Hide unused pool slots (those that were *not* touched this frame)
            for i in range(self.max_paths):
                if i not in path_used_this_frame and path_state[i].display != "none":
                    cmds.append(f"path_pool[{i}].style.display = 'none';")
                    path_state[i].display = "none"
            for i in range(self.max_circles):
                if i not in circle_used_this_frame and circ_state[i].display != "none":
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

        # Build small optimization context
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
        
        self.debug = False

        self.basename = scene.__class__.__name__
        self.html_path = os.path.join("media", "svg_animations", self.basename + ".html")
        self.js_path = os.path.join("media", "svg_animations", self.basename + ".js")

        self.frame_index = 0
        
        # {uuid: [frame_0_data, frame_1_data, ...]}, frame data is None for frames that don't have this object
        self.tracked_objects: Dict[str, List[Dict[str, str] | None]] = {}
        
        # {frame_0_meta, frame_1_meta, ...}
        self.scene_frames: List[_SceneFrameMeta] = []
        self.collecting = True

        # Parallel machinery ----------------------------------------------------
        # Each element: (frame_idx, tmp_svg_path) ; the VMobject copy itself is
        # kept inside the task to keep _svg_paths tiny.
        self._svg_paths: Dict[int, str] = {}
        # Each batch entry: (frame_idx, vm_pickle_bytes, tmp_svg_path)
        self._batch: List[Tuple[int, bytes, str]] = []
        self._workers: List[Process] = []
        self.batch_size = 25

        self.orig_w = scene.camera.frame_width
        self.orig_h = scene.camera.frame_height

        # Snapshot the current manim configuration so that worker processes
        # render with **exactly** the same pixel/frame size etc.  We only
        # need a handful of numeric values – cloudpickle keeps it trivial.
        from manim import config as _mconf  # local import to avoid cycle at top
        self._cfg_bytes: bytes = cloudpickle.dumps(_mconf)

        self._write_html_shell()
        scene.add_updater(self._frame_updater)  # type: ignore[arg-type]

    def _frame_updater(self, _dt: float) -> None:
        if not self.collecting:
            return

        # Snapshot VMobject 
        vm_copy = deepcopy(self.vmobject)

        # Decide filename now so we can order later.
        tmp_svg_path = os.path.join(os.getcwd(), "tempout", f"{self.basename}_{self.frame_index}.svg")
        self._svg_paths[self.frame_index] = tmp_svg_path

        # Serialize VMobject with cloudpickle so lambdas are handled.
        vm_serialized: bytes = cloudpickle.dumps(vm_copy)

        # Queue for background export (only bytes – picklable by stdlib)
        self._batch.append((self.frame_index, vm_serialized, tmp_svg_path))
        if len(self._batch) >= self.batch_size:
            self._spawn_worker(self._batch)
            self._batch = []

        # Capture scene‑wide metadata.
        cam = self.scene.camera
        bg_rgba = color_to_int_rgba(cam.background_color, cam.background_opacity)
        bg_rgba[-1] /= 255
        bg_str = f"rgb({', '.join(map(str, bg_rgba))})"

        viewbox = None
        if isinstance(self.scene, MovingCameraScene):
            pw = cam.pixel_width * cam.frame_width / self.orig_w
            ph = cam.pixel_height * cam.frame_height / self.orig_h
            top_l = cam.frame.get_corner(UL) * cam.pixel_width / self.orig_w
            center = top_l + cam.pixel_width / 2 * RIGHT + cam.pixel_height / 2 * DOWN
            center[1] = -center[1]  # SVG Y is inverted
            viewbox = list(map(str, [*center[:2], pw, ph]))

        self.scene_frames.append(_SceneFrameMeta(bg=bg_str, viewbox=viewbox))

        # Advance frame counter.
        self.frame_index += 1

    # -------------------------------------------------------------------------
    @staticmethod
    def _worker(batch: List[Tuple[int, bytes, str]], cfg_bytes: bytes) -> None:  # child process
        """Render each VMobject (sent as *cloudpickle* bytes) to SVG - heavy Cairo work."""
        import cloudpickle  # re-import inside subprocess (safe even if absent globally)
        # Apply main-process manim config first.
        from manim import config as _mconf  # noqa: N812 – keep camel for parity with manim

        _cfg = cloudpickle.loads(cfg_bytes)
        _mconf.update(_cfg)

        # Lazy import of heavy SVG helper *after* config so it sees correct values
        from forked_svg import create_svg_from_vgroup

        for _idx, vm_bytes, path in batch:
            try:
                vm_copy = cloudpickle.loads(vm_bytes)
            except Exception as exc:  # pragma: no cover – shouldn't happen
                print(f"[worker] Failed to unpickle VMobject: {exc}")
                continue

            # The helper handles its own tempfiles etc.
            create_svg_from_vgroup(vm_copy, path)

    def _spawn_worker(self, batch: List[Tuple[int, bytes, str]]) -> None:
        """Fork a *detached* process executing :py:meth:`_worker`."""
        # Each worker gets its *own* copy of the batch list (pickle serialized).
        p = Process(target=self._worker, args=(batch, self._cfg_bytes))
        p.daemon = True  # die with parent even if we forget join()
        p.start()
        self._workers.append(p)
    # -------------------------------------------------------------------------
    # Original per‑frame SVG parsing logic – copied verbatim and put behind
    # *_parse_frame* so that it can be called once all SVGs exist.
    # -------------------------------------------------------------------------
    def _parse_frame(self, frame_idx: int, svg_path: str) -> None:
        current_frame_svg_data: Dict[str, Dict[str, str]] = {}

        try:
            tree = ET.parse(svg_path)
            root = tree.getroot()
            ns_uri = "http://www.w3.org/2000/svg"
            if root.tag.startswith("{"):
                end = root.tag.find("}")
                if end != -1:
                    ns_uri = root.tag[1:end]
            ns = {"svg": ns_uri}

            for path_element in root.findall(".//svg:path[@id]", ns):
                uuid_str = path_element.get("id")
                if not uuid_str:
                    # Skip malformed element.
                    continue

                raw_attr = dict(path_element.attrib)
                entry: Dict[str, str] = {}

                # Shape detection
                path_def = str(raw_attr.get("d", ""))
                circle_params = _detect_circle(path_def)
                if circle_params:
                    cx, cy, r = circle_params
                    entry.update({
                        "_shape": "circle",
                        "cx": _round_value("cx", str(cx)),
                        "cy": _round_value("cy", str(cy)),
                        "r": _round_value("r", str(r)),
                    })
                else:
                    entry["_shape"] = "path"

                # Attributes
                for k, v_obj in raw_attr.items():
                    if k == "id":
                        if self.debug:
                            entry["id"] = v_obj
                    v = str(v_obj)
                    if k == "d":
                        if entry["_shape"] == "path":
                            entry["d"] = _round_value("d", v)
                        continue
                    if entry["_shape"] == "circle" and k in ("cx", "cy", "r"):
                        continue
                    entry[k] = _round_value(k, v)

                current_frame_svg_data[uuid_str] = entry

        except (ET.ParseError, FileNotFoundError) as exc:
            print(f"[HTMLParsedVMobjectParallel] Failed to parse SVG for frame {frame_idx}: {exc}")
            # Treat as blank frame.

        # ------------------------------------------------------------------
        # Update tracking dict – identical logic as original implementation.
        # ------------------------------------------------------------------
        all_uuids = set(self.tracked_objects.keys()).union(current_frame_svg_data.keys())
        for uuid_str in all_uuids:
            if uuid_str not in self.tracked_objects:
                # New object – pad earlier frames with None.
                self.tracked_objects[uuid_str] = [None] * frame_idx

            history = self.tracked_objects[uuid_str]
            # Ensure history length matches |frame_idx| (may have gaps if the
            # object vanished for a few frames).
            if len(history) < frame_idx:
                history.extend([None] * (frame_idx - len(history)))

            # Append this frame's data (or None if missing).
            history.append(current_frame_svg_data.get(uuid_str))


    def finish(self):
        """Stop collection, run compilation pipeline, write .js / .html."""
        # Freeze data collection
        if self.collecting:
            self.scene.remove_updater(self._frame_updater)  # type: ignore[arg-type]
            self.collecting = False
        num_frames = self.frame_index
        
        #-------------------------------------------------------------------------
        # Block until every worker has completed, then post‑process frames.
        # Flush leftovers < BATCH_SIZE.
        if self._batch:
            self._spawn_worker(self._batch)
            self._batch = []

        # Wait for all workers.
        for p in self._workers:
            p.join()

        # Sequentially parse SVGs to populate tracking structures.
        total_frames = self.frame_index  # already incremented in updater
        for idx in range(total_frames):
            svg_path = self._svg_paths[idx]
            self._parse_frame(idx, svg_path)
        #-------------------------------------------------------------------------

        # Build per-frame JS arrays 
        builder = _JSFrameBuilder(
            tracked_objects=self.tracked_objects,
            scene_frames=self.scene_frames,
            svg_var=self.basename.lower(),
            scene_name=self.basename,
        )
        element_decls, frames_js, opt_ctx = builder.build_frames()

        # Optimizer pipeline
        for optim in _OPTIMIZERS:
            maybe_new = optim(frames_js, opt_ctx) or frames_js
            # ensure *exact* same nested list structure if pass returns None
            frames_js = maybe_new

        # Serialize JS / HTML
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