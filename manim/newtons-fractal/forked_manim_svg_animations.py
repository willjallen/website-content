from manim import *
from manim_mobject_svg import *
from forked_svg import *
from svgpathtools import parse_path
import os
import re
import math
import numpy as np
import xml.etree.ElementTree as ET
import tempfile
from pathlib import Path


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
</head>
<body style="background-color:black;">
    <svg id="{svg_id}" width="{width}" viewBox="0 0 {w_px} {h_px}" style="background-color:{bg};"></svg>
    {extra_body}
    <script src="{js_file}"></script>
</body>
</html>"""

SIMPLE_HTML_TEMPLATE = """<div>
    <svg id="{svg_id}" width="{width}" viewBox="0 0 {w_px} {h_px}" style="background-color:{bg};"></svg>
</div>"""

JS_WRAPPER = """let rendered = false;
let playing  = false;
const {svg_var} = document.getElementById("{svg_id}");
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

class HTMLParsedVMobject:
    """
    Collects per-frame SVG snapshots from a Manim VMobject, diffs attributes,
    and emits:
    - an HTML file that embeds the SVG container
    - a JavaScript file containing one updater function per frame

    The JS side reuses a fixed pool of <path> and <circle> elements,
    setting only attributes that actually change between frames.
    """

    def __init__(self, vmobject: VMobject, scene: Scene,
                 width: str = "500px", basic_html: bool = False):
        self.vmobject       = vmobject
        self.scene          = scene
        self.width          = width
        self.basic_html     = basic_html

        self.basename       = scene.__class__.__name__
        self.html_path      = os.path.join("media", "svg_animations", self.basename + ".html")
        self.js_path        = os.path.join("media", "svg_animations", self.basename + ".js")

        self.frame_index    = 0
        self.tracked_objects: dict[str, list[dict | None]] = {}
        self.scene_level_data: list[dict] = []
        self.collecting     = True

        self.orig_w         = scene.camera.frame_width
        self.orig_h         = scene.camera.frame_height

        self._write_html_shell()                    # pre-compute HTML template
        scene.add_updater(self._frame_updater)

    # --------------------------------------------------------------------- #
    #                Helpers: geometry rounding / SVG parsing               #
    # --------------------------------------------------------------------- #
    def _detect_circle(self, path_d: str, tol: float = 1e-2):
        """
        Try to fit an SVG path to a circle; return (cx, cy, r) on success.
        Use simple algebraic least-squares fit, bail out if error exceeds tol.
        """
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
        b = -(X**2 + Y**2)
        try:
            (A, B, C), *_ = np.linalg.lstsq(M, b, rcond=None)
        except np.linalg.LinAlgError:
            return None

        cx, cy = -A / 2, -B / 2
        r2     = (A**2 + B**2) / 4 - C
        if r2 <= max(tol**2 * 0.01, 1e-9):
            return None
        r = math.sqrt(r2)

        if any(abs(math.hypot(p.real - cx, p.imag - cy) - r) > tol for p in samples):
            return None
        return cx, cy, r

    @staticmethod
    def _round_value(attr: str, value: str, precision: int = 2) -> str:
        """Round numeric SVG attribute strings for stability and compression."""
        if attr == "d":                                # path data → round every number
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
            out  = []
            for i, n in enumerate(nums):
                if n.endswith("%"):
                    out.append(f"{round(float(n[:-1]), precision)}%")
                else:
                    out.append(str(round(float(n), precision if head == "rgba(" and i == 3 else 0)))
            return head + ", ".join(out) + ")"
        return value

    # --------------------------------------------------------------------- #
    #                       Per-frame data collection                       #
    # --------------------------------------------------------------------- #
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
                    circle_params = self._detect_circle(path_def)
                    if circle_params:
                        cx, cy, r = circle_params
                        entry["_shape"] = "circle"
                        entry["cx"] = self._round_value("cx", str(cx))
                        entry["cy"] = self._round_value("cy", str(cy))
                        entry["r"]  = self._round_value("r",  str(r))
                    else:
                        entry["_shape"] = "path"
                        entry["d"] = self._round_value("d", path_def)
                    for k, v in raw_attr.items():
                        if k == "d":
                            if entry["_shape"] == "path" and "d" not in entry:
                                entry["d"] = self._round_value("d", path_def)
                            continue
                        entry[k] = self._round_value(k, str(v))
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

        self.scene_level_data.append({
            "bg": bg_str,
            "viewbox": viewbox
        })
        self.frame_index += 1

    # --------------------------------------------------------------------- #
    #                             HTML scaffold                             #
    # --------------------------------------------------------------------- #
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

    # --------------------------------------------------------------------- #
    #                          Compilation to files                         #
    # --------------------------------------------------------------------- #
    def finish(self):
        """Stop collecting, diff frames, write *.js and *.html output files."""
        self.scene.remove_updater(self._frame_updater)
        self.collecting = False

        svg_var = self.basename.lower()
        all_uuids = list(self.tracked_objects.keys())
        num_frames = self.frame_index

        if num_frames == 0 and not all_uuids:
            print(f"Warning: No animation data collected for {self.basename}.")
            os.makedirs(os.path.dirname(self.js_path), exist_ok=True)
            # Corrected element_declarations formatting for empty case
            empty_element_decls = "    const path_pool = [];\n    const circle_pool = [];"
            empty_js_code = JS_WRAPPER.format(
                svg_var=svg_var,
                svg_id=self.basename,
                element_declarations=empty_element_decls,
                frames_array="const frames = [];",
                scene_name=self.basename
            )
            with open(self.js_path, "w") as f_js:
                f_js.write(empty_js_code)
            with open(self.html_path, "w") as f_html:
                f_html.write(self.html_markup)
            return

        max_simultaneous_paths = 0
        max_simultaneous_circles = 0
        for i in range(num_frames):
            paths_in_frame = 0
            circles_in_frame = 0
            for uuid in all_uuids:
                if i < len(self.tracked_objects[uuid]):
                    obj_data = self.tracked_objects[uuid][i]
                    if obj_data:
                        if obj_data.get("_shape") == "circle":
                            circles_in_frame += 1
                        else:
                            paths_in_frame += 1
            max_simultaneous_paths = max(max_simultaneous_paths, paths_in_frame)
            max_simultaneous_circles = max(max_simultaneous_circles, circles_in_frame)

        py_path_pool_element_states = [{} for _ in range(max_simultaneous_paths)]
        py_circle_pool_element_states = [{} for _ in range(max_simultaneous_circles)]
        py_scene_bg_state = None
        py_scene_viewbox_state = None

        all_frames_js_code_blocks: list[list[str]] = []

        # Corrected element_declarations formatting for the JS_WRAPPER
        element_decls_js = (
            "    const path_pool = [];\n"
            "    const circle_pool = [];"
        )
        
        initial_js_setup_commands = ["while (path_pool.length) { path_pool.pop(); }", "while (circle_pool.length) { circle_pool.pop(); }", f"{svg_var}.replaceChildren();"]
        for i in range(max_simultaneous_paths):
            initial_js_setup_commands.extend([
                f"const p{i} = document.createElementNS('http://www.w3.org/2000/svg','path');",
                f"{svg_var}.appendChild(p{i});",
                f"path_pool.push(p{i});"
            ])
        for i in range(max_simultaneous_circles):
            initial_js_setup_commands.extend([
                f"const c{i} = document.createElementNS('http://www.w3.org/2000/svg','circle');",
                f"{svg_var}.appendChild(c{i});",
                f"circle_pool.push(c{i});"
            ])

        for frame_idx in range(num_frames):
            js_commands_for_this_frame: list[str] = []
            if frame_idx == 0:
                js_commands_for_this_frame.extend(initial_js_setup_commands)

            path_pool_slot_idx = 0
            circle_pool_slot_idx = 0
            active_pooled_elements_this_frame = set()

            for uuid in all_uuids:
                current_uuid_attrs = None
                if frame_idx < len(self.tracked_objects[uuid]):
                    current_uuid_attrs = self.tracked_objects[uuid][frame_idx]

                if current_uuid_attrs:
                    shape = current_uuid_attrs.get("_shape", "path")
                    py_pool_state_list_ref = None
                    js_element_name = ""
                    assigned_slot = -1

                    if shape == "path":
                        if path_pool_slot_idx < max_simultaneous_paths:
                            assigned_slot = path_pool_slot_idx
                            js_element_name = f"path_pool[{assigned_slot}]"
                            py_pool_state_list_ref = py_path_pool_element_states
                            path_pool_slot_idx += 1
                        else:
                            print(f"Warning Frame {frame_idx}: Ran out of path pool slots for UUID {uuid}. Max: {max_simultaneous_paths}")
                            continue
                    else: # circle
                        if circle_pool_slot_idx < max_simultaneous_circles:
                            assigned_slot = circle_pool_slot_idx
                            js_element_name = f"circle_pool[{assigned_slot}]"
                            py_pool_state_list_ref = py_circle_pool_element_states
                            circle_pool_slot_idx += 1
                        else:
                            print(f"Warning Frame {frame_idx}: Ran out of circle pool slots for UUID {uuid}. Max: {max_simultaneous_circles}")
                            continue
                    
                    active_pooled_elements_this_frame.add((shape, assigned_slot))
                    current_element_py_state = py_pool_state_list_ref[assigned_slot]
                    attrs_to_set_in_js = {}

                    for k_attr, v_attr_actual in current_uuid_attrs.items():
                        if k_attr == "_shape": continue
                        v_attr_str = str(v_attr_actual)
                        attrs_to_set_in_js[k_attr] = v_attr_str
                        if current_element_py_state.get(k_attr) != v_attr_str:
                            escaped_v = v_attr_str.replace("\\", "\\\\").replace("'", "\\'")
                            js_commands_for_this_frame.append(f"{js_element_name}.setAttribute('{k_attr}', '{escaped_v}');")
                            current_element_py_state[k_attr] = v_attr_str

                    for k_attr_prev in list(current_element_py_state.keys()):
                        if k_attr_prev not in attrs_to_set_in_js and k_attr_prev != "style.display":
                            js_commands_for_this_frame.append(f"{js_element_name}.removeAttribute('{k_attr_prev}');")
                            del current_element_py_state[k_attr_prev]
                    
                    if current_element_py_state.get("style.display") != "":
                        js_commands_for_this_frame.append(f"{js_element_name}.style.display = '';")
                        current_element_py_state["style.display"] = ""
            
            for slot_idx_path in range(max_simultaneous_paths):
                if ("path", slot_idx_path) not in active_pooled_elements_this_frame:
                    if py_path_pool_element_states[slot_idx_path].get("style.display") != "none":
                        js_commands_for_this_frame.append(f"path_pool[{slot_idx_path}].style.display = 'none';")
                        py_path_pool_element_states[slot_idx_path]["style.display"] = "none"
            
            for slot_idx_circle in range(max_simultaneous_circles):
                if ("circle", slot_idx_circle) not in active_pooled_elements_this_frame:
                    if py_circle_pool_element_states[slot_idx_circle].get("style.display") != "none":
                        js_commands_for_this_frame.append(f"circle_pool[{slot_idx_circle}].style.display = 'none';")
                        py_circle_pool_element_states[slot_idx_circle]["style.display"] = "none"
            
            if frame_idx < len(self.scene_level_data):
                scene_data_this_frame = self.scene_level_data[frame_idx]
                current_bg = scene_data_this_frame.get("bg")
                if current_bg != py_scene_bg_state:
                    js_commands_for_this_frame.append(f"{svg_var}.style.backgroundColor='{current_bg}';")
                    py_scene_bg_state = current_bg
                
                current_viewbox = scene_data_this_frame.get("viewbox")
                if current_viewbox != py_scene_viewbox_state:
                    if current_viewbox:
                        vb_str = " ".join(map(str, current_viewbox))
                        js_commands_for_this_frame.append(f"{svg_var}.setAttribute('viewBox','{vb_str}');")
                    else:
                        js_commands_for_this_frame.append(f"{svg_var}.removeAttribute('viewBox');")
                    py_scene_viewbox_state = current_viewbox

            all_frames_js_code_blocks.append(js_commands_for_this_frame)

        frame_function_bodies = []
        for idx, body_commands in enumerate(all_frames_js_code_blocks):
            indented_commands = "\n        ".join(body_commands)
            frame_function_bodies.append(f"    () => {{\n        // Frame {idx}\n        {indented_commands}\n    }}")
        
        frames_array_js = "const frames = [\n" + ",\n".join(frame_function_bodies) + "\n];"

        js_code = JS_WRAPPER.format(
            svg_var=svg_var,
            svg_id=self.basename,
            element_declarations=element_decls_js,
            frames_array=frames_array_js,
            scene_name=self.basename
        )
        os.makedirs(os.path.dirname(self.js_path), exist_ok=True)
        with open(self.js_path, "w") as f_js:
            f_js.write(js_code)
        with open(self.html_path, "w") as f_html:
            f_html.write(self.html_markup)
