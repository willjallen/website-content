from manim import *
from manim_mobject_svg import *
from svgpathtools import svg2paths, parse_path
import os
import re
import math
import numpy as np


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
            frames[i++]();        // run one frame’s updater
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
    – an HTML file that embeds the SVG container
    – a JavaScript file containing one updater function per frame

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
        self.frames_data: list[dict] = []           # collected frame metadata
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
        """Called each render tick by Manim – serialize current VMobject to SVG."""
        if not self.collecting:
            return

        tmp_svg = f"{self.basename}_{self.frame_index}.svg"
        self.vmobject.to_svg(tmp_svg)                 # create snapshot file
        _, attrs_list = svg2paths(tmp_svg)
        os.remove(tmp_svg)

        # Build list of element attribute dictionaries for this frame
        elem_attrs: list[dict] = []
        for raw_attr in attrs_list:
            entry = {}
            if "d" in raw_attr:
                path_def = str(raw_attr["d"])
                circle = self._detect_circle(path_def)
                if circle:
                    cx, cy, r = circle
                    entry["_shape"] = "circle"
                    entry["cx"] = self._round_value("cx", str(cx))
                    entry["cy"] = self._round_value("cy", str(cy))
                    entry["r"]  = self._round_value("r",  str(r))
                else:
                    entry["_shape"] = "path"
                    entry["d"] = self._round_value("d", path_def)
            for k, v in raw_attr.items():
                if k == "d":
                    continue
                entry[k] = self._round_value(k, str(v))
            if "_shape" not in entry:
                entry["_shape"] = "path"
            elem_attrs.append(entry)

        # scene-wide metadata
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
            center[1] = -center[1]
            viewbox = list(map(str, [*center[:2], pw, ph]))

        self.frames_data.append({
            "elements": elem_attrs,
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

        # Pre-scan frames to allocate fixed pools of <path>/<circle> elements
        max_paths   = max((sum(e["_shape"] == "path"   for e in f["elements"])
                           for f in self.frames_data), default=0)
        max_circles = max((sum(e["_shape"] == "circle" for e in f["elements"])
                           for f in self.frames_data), default=0)

        # Declare JS handles for every pooled element
        decls  = ["// path pool"]
        decls += [f"let p_{i};" for i in range(max_paths)]
        decls += ["// circle pool"]
        decls += [f"let c_{i};" for i in range(max_circles)]
        element_decls_js = "\n".join("    " + d for d in decls)

        # Walk through frames, emit diff-only JS snippets
        frame_bodies: list[str] = []
        prev_path_attrs:   list[dict] = []
        prev_circle_attrs: list[dict] = []
        hidden_paths   = [False] * max_paths
        hidden_circles = [False] * max_circles
        prev_bg        = None
        prev_viewbox   = None

        for idx, frame in enumerate(self.frames_data):
            body_lines: list[str] = []

            # First frame: build the element pool once
            if idx == 0:
                body_lines.append(f"{svg_var}.replaceChildren();")
                for i in range(max_paths):
                    body_lines += [
                        f"p_{i}=document.createElementNS('http://www.w3.org/2000/svg','path');",
                        f"{svg_var}.appendChild(p_{i});"
                    ]
                for i in range(max_circles):
                    body_lines += [
                        f"c_{i}=document.createElementNS('http://www.w3.org/2000/svg','circle');",
                        f"{svg_var}.appendChild(c_{i});"
                    ]

            # Split current frame’s attributes into path/circle lists
            paths_now   = [e for e in frame["elements"] if e["_shape"] == "path"]
            circles_now = [e for e in frame["elements"] if e["_shape"] == "circle"]

            # Diff path pool
            for i in range(max_paths):
                el_js = f"p_{i}"
                if i < len(paths_now):
                    cur = paths_now[i]
                    prev = prev_path_attrs[i] if i < len(prev_path_attrs) else {}

                    # set changed / new attributes
                    for k, v in cur.items():
                        if k == "_shape":
                            continue
                        if prev.get(k) != v:
                            v_esc = v.replace("\\", "\\\\").replace("'", "\\'")
                            body_lines.append(f"{el_js}.setAttribute('{k}','{v_esc}');")

                    # remove stale attributes
                    for k in prev:
                        if k not in cur and k != "_shape":
                            body_lines.append(f"{el_js}.removeAttribute('{k}');")

                    if hidden_paths[i]:
                        body_lines.append(f"{el_js}.style.display='';")
                        hidden_paths[i] = False
                else:  # unused in this frame
                    if not hidden_paths[i]:
                        body_lines.append(f"{el_js}.style.display='none';")
                        hidden_paths[i] = True

            # Diff circle pool (same logic)
            for i in range(max_circles):
                el_js = f"c_{i}"
                if i < len(circles_now):
                    cur = circles_now[i]
                    prev = prev_circle_attrs[i] if i < len(prev_circle_attrs) else {}
                    for k, v in cur.items():
                        if k == "_shape":
                            continue
                        if prev.get(k) != v:
                            v_esc = v.replace("\\", "\\\\").replace("'", "\\'")
                            body_lines.append(f"{el_js}.setAttribute('{k}','{v_esc}');")
                    for k in prev:
                        if k not in cur and k != "_shape":
                            body_lines.append(f"{el_js}.removeAttribute('{k}');")
                    if hidden_circles[i]:
                        body_lines.append(f"{el_js}.style.display='';")
                        hidden_circles[i] = False
                else:
                    if not hidden_circles[i]:
                        body_lines.append(f"{el_js}.style.display='none';")
                        hidden_circles[i] = True

            # Scene-level changes
            if frame["bg"] != prev_bg:
                body_lines.append(f"{svg_var}.style.backgroundColor='{frame['bg']}';")
                prev_bg = frame["bg"]

            if frame["viewbox"] != prev_viewbox:
                if frame["viewbox"]:
                    vb_str = " ".join(frame["viewbox"])
                    body_lines.append(f"{svg_var}.setAttribute('viewBox','{vb_str}');")
                prev_viewbox = frame["viewbox"]

            # Save JS body for this frame
            frame_bodies.append("\n        ".join(body_lines) or "// no-op")

            # Snapshot current attr lists for next diff
            prev_path_attrs   = [dict(a) for a in paths_now]
            prev_circle_attrs = [dict(a) for a in circles_now]

        # Build JS array literal: one function per frame
        frames_array_js = "const frames = [\n" + ",\n".join(
            f"    () => {{\n        {body}\n    }}" for body in frame_bodies
        ) + "\n];"

        # Final JS file
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
