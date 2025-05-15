from manim import *
from manim_mobject_svg import *
from svgpathtools import svg2paths, parse_path
import itertools
import os
import re
import math
import numpy as np


HTML_STRUCTURE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>%s</title>
</head>
<body style="background-color: black;">
    <svg id="%s" width="%s" viewBox="0 0 %d %d" style="background-color:%s;"></svg>
    %s
    <script src="%s"></script>
</body>
</html>"""


BASIC_HTML_STRUCTURE = """<div>
    <svg id="%s" width="%s" viewBox="0 0 %d %d" style="background-color:%s;"></svg>
</div>"""


JAVASCRIPT_STRUCTURE = """var rendered = false;
var playing = false;
var %s = document.getElementById("%s");
%s
%s
function render%s() {
    if (playing) return;
    playing = true;
    rendered = false;
    let f = 0;
    function step() {
        if (f < frames.length) {
            frames[f]();
            f++;
            requestAnimationFrame(step);
        } else {
            playing = false;
            rendered = true;
        }
    }
    requestAnimationFrame(step);
}"""


class HTMLParsedVMobject:
    def __init__(self, vmobject: VMobject, scene: Scene, width: float = "500px", basic_html=False):
        self.vmobject = vmobject
        self.scene = scene
        self.filename_base = scene.__class__.__name__
        self.html_filename = os.path.join('media', 'svg_animations', self.filename_base + '.html')
        self.js_filename = os.path.join('media', 'svg_animations', self.filename_base + '.js')
        self.current_index = 0
        self.final_html_body = ""
        self.width = width
        self.basic_html = basic_html
        self.update_html()
        self.frames_data = []
        self.continue_updating = True
        self.original_frame_width = self.scene.camera.frame_width
        self.original_frame_height = self.scene.camera.frame_height
        self.scene.add_updater(self.updater)

    def _detect_circle_from_path(self, d: str, tol: float = 1e-2):
        if not d:
            return None
        try:
            path = parse_path(d)
        except Exception:
            return None
        if len(path) == 0 or not path.iscontinuous() or not path.isclosed():
            return None
        sampled = set()
        for seg in path:
            if hasattr(seg, 'start') and hasattr(seg, 'point') and hasattr(seg, 'end'):
                sampled.update([seg.start, seg.point(0.5), seg.end])
            else:
                return None
        if len(sampled) < 3:
            return None
        pts = np.array([(p.real, p.imag) for p in sampled])
        x, y = pts[:, 0], pts[:, 1]
        M = np.vstack([x, y, np.ones(len(pts))]).T
        P = -(x ** 2 + y ** 2)
        try:
            (A, B, C), *_ = np.linalg.lstsq(M, P, rcond=None)
        except np.linalg.LinAlgError:
            return None
        cx, cy = -A / 2, -B / 2
        r2 = (A ** 2 + B ** 2) / 4 - C
        if r2 <= max(tol * tol * 0.01, 1e-9):
            return None
        r = math.sqrt(r2)
        if r < tol / 2:
            return None
        for p in sampled:
            if abs(math.hypot(p.real - cx, p.imag - cy) - r) > tol:
                return None
        try:
            length_err_tol = max(tol * 0.1, 1e-7)
            if abs(path.length(error=length_err_tol) - 2 * math.pi * r) > max(tol * 10, 0.15 * r):
                return None
        except Exception:
            return None
        return cx, cy, r

    def _round_attribute_value(self, key: str, value_str: str, precision: int = 2) -> str:
        if not isinstance(value_str, str):
            return value_str
        if key == 'd':
            def repl(m):
                try:
                    return str(round(float(m.group()), precision))
                except ValueError:
                    return m.group()
            return re.sub(r"[+-]?\d*\.?\d+(?:[eE][+-]?\d+)?", repl, value_str)
        if key in {'fill-opacity', 'stroke-opacity', 'stroke-width', 'opacity', 'stroke-miterlimit', 'cx', 'cy', 'r'}:
            try:
                num = float(value_str)
                if 0 < abs(num) < 1:
                    s = str(num)
                    dec = s.split('.', 1)[1] if '.' in s else ''
                    leading = len(dec) - len(dec.lstrip('0'))
                    return str(round(num, leading + 2))
                return str(round(num, precision))
            except ValueError:
                return value_str
        if value_str.startswith(('rgb(', 'rgba(')):
            pre = 'rgba(' if value_str.startswith('rgba(') else 'rgb('
            content = value_str[len(pre):-1]
            parts = [p.strip() for p in content.split(',')]
            out = []
            for i, p in enumerate(parts):
                if p.endswith('%'):
                    try:
                        out.append(f"{round(float(p[:-1]), precision)}%")
                    except ValueError:
                        out.append(p)
                else:
                    try:
                        num = float(p)
                        if pre == 'rgba(' and i == 3:
                            out.append(str(round(num, precision)))
                        else:
                            out.append(str(int(round(num))))
                    except ValueError:
                        out.append(p)
            return pre + ', '.join(out) + ')'
        return value_str

    def _escape_js_string(self, value: str) -> str:
        return value.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')

    def updater(self, dt):
        if not self.continue_updating:
            return
        svg_name = f"{self.filename_base}{self.current_index}.svg"
        self.vmobject.to_svg(svg_name)
        _, attr_list = svg2paths(svg_name)
        frame_attrs = []
        for attrs in attr_list:
            new = {}
            if 'd' in attrs:
                dval = str(attrs['d'])
                circ = self._detect_circle_from_path(dval)
                if circ:
                    cx, cy, r = circ
                    new['_shape_type'] = 'circle'
                    new['cx'] = self._round_attribute_value('cx', str(cx))
                    new['cy'] = self._round_attribute_value('cy', str(cy))
                    new['r'] = self._round_attribute_value('r', str(r))
                else:
                    new['_shape_type'] = 'path'
                    new['d'] = self._round_attribute_value('d', dval)
            for k, v in attrs.items():
                if k == 'd':
                    continue
                new[k] = self._round_attribute_value(k, str(v))
            if '_shape_type' not in new:
                new['_shape_type'] = 'path'
            frame_attrs.append(new)
        bg = color_to_int_rgba(self.scene.camera.background_color, self.scene.camera.background_opacity)
        bg[-1] /= 255
        bg_str = f"rgb({', '.join(map(str, bg))})"
        vb_arr = None
        if isinstance(self.scene, MovingCameraScene):
            frame = self.scene.camera.frame
            pw = self.scene.camera.pixel_width * self.scene.camera.frame_width / self.original_frame_width
            ph = self.scene.camera.pixel_height * self.scene.camera.frame_height / self.original_frame_height
            pc = frame.get_corner(UL) * self.scene.camera.pixel_width / self.original_frame_width
            pc += self.scene.camera.pixel_width / 2 * RIGHT + self.scene.camera.pixel_height / 2 * DOWN
            pc[1] = -pc[1]
            vb_arr = list(map(str, [*pc[:2], pw, ph]))
        self.frames_data.append({'attributes': frame_attrs, 'background_color_str': bg_str,
                                 'viewBox_str_array': vb_arr})
        self.current_index += 1
        os.remove(svg_name)

    def update_html(self):
        bg = color_to_int_rgba(self.scene.camera.background_color, self.scene.camera.background_opacity)
        bg[-1] /= 255
        bg_str = f"rgb({', '.join(map(str, bg))})"
        if not self.basic_html:
            self.html = HTML_STRUCTURE % (self.filename_base, self.filename_base, self.width,
                                          self.scene.camera.pixel_width, self.scene.camera.pixel_height,
                                          bg_str, self.final_html_body, os.path.basename(self.js_filename))
        else:
            self.html = BASIC_HTML_STRUCTURE % (self.filename_base, self.width,
                                                self.scene.camera.pixel_width, self.scene.camera.pixel_height, bg_str)

    def finish(self):
        self.scene.remove_updater(self.updater)
        svg_var = self.filename_base.lower()
        max_paths = max(sum(1 for a in f['attributes'] if a['_shape_type'] == 'path') for f in self.frames_data) if self.frames_data else 0
        max_circles = max(sum(1 for a in f['attributes'] if a['_shape_type'] == 'circle') for f in self.frames_data) if self.frames_data else 0
        vars_js = "    // Path elements\n"
        vars_js += ''.join(f"    var p_el{i};\n" for i in range(max_paths))
        vars_js += "    // Circle elements\n"
        vars_js += ''.join(f"    var c_el{i};\n" for i in range(max_circles))
        frames_list = []
        prev_path_attrs = []
        prev_circle_attrs = []
        path_hidden = [False] * max_paths
        circle_hidden = [False] * max_circles
        prev_bg = None
        prev_vb = None
        for idx, frame in enumerate(self.frames_data):
            path_attrs = [d for d in frame['attributes'] if d['_shape_type'] == 'path']
            circ_attrs = [d for d in frame['attributes'] if d['_shape_type'] == 'circle']
            js = ""
            if idx == 0:
                js += f"        {svg_var}.replaceChildren();\n"
                for i in range(max_paths):
                    js += f"        p_el{i}=document.createElementNS('http://www.w3.org/2000/svg','path');\n"
                    js += f"        {svg_var}.appendChild(p_el{i});\n"
                for i in range(max_circles):
                    js += f"        c_el{i}=document.createElementNS('http://www.w3.org/2000/svg','circle');\n"
                    js += f"        {svg_var}.appendChild(c_el{i});\n"
            for i in range(max_paths):
                el = f"p_el{i}"
                if i < len(path_attrs):
                    cur = path_attrs[i]
                    prev = prev_path_attrs[i] if i < len(prev_path_attrs) else {}
                    for k, v in cur.items():
                        if k == '_shape_type':
                            continue
                        if str(prev.get(k)) != str(v):
                            js += f"        {el}.setAttribute('{k}','{self._escape_js_string(v)}');\n"
                    for k in prev:
                        if k not in cur and k != '_shape_type':
                            js += f"        {el}.removeAttribute('{k}');\n"
                    if path_hidden[i]:
                        js += f"        {el}.style.display='';\n"
                        path_hidden[i] = False
                else:
                    if not path_hidden[i]:
                        js += f"        {el}.style.display='none';\n"
                        path_hidden[i] = True
            for i in range(max_circles):
                el = f"c_el{i}"
                if i < len(circ_attrs):
                    cur = circ_attrs[i]
                    prev = prev_circle_attrs[i] if i < len(prev_circle_attrs) else {}
                    for k, v in cur.items():
                        if k == '_shape_type':
                            continue
                        if str(prev.get(k)) != str(v):
                            js += f"        {el}.setAttribute('{k}','{self._escape_js_string(v)}');\n"
                    for k in prev:
                        if k not in cur and k != '_shape_type':
                            js += f"        {el}.removeAttribute('{k}');\n"
                    if circle_hidden[i]:
                        js += f"        {el}.style.display='';\n"
                        circle_hidden[i] = False
                else:
                    if not circle_hidden[i]:
                        js += f"        {el}.style.display='none';\n"
                        circle_hidden[i] = True
            if frame['background_color_str'] != prev_bg:
                js += f"        {svg_var}.style.backgroundColor='{frame['background_color_str']}';\n"
                prev_bg = frame['background_color_str']
            if frame['viewBox_str_array'] != prev_vb:
                if frame['viewBox_str_array']:
                    vb = ' '.join(frame['viewBox_str_array'])
                    js += f"        {svg_var}.setAttribute('viewBox','{vb}');\n"
                prev_vb = frame['viewBox_str_array']
            frames_list.append(js.rstrip())
            prev_path_attrs = [dict(a) for a in path_attrs]
            prev_circle_attrs = [dict(a) for a in circ_attrs]
        frames_js = "var frames=[\n" + ",\n".join(f"    function(){{\n{s}\n    }}" for s in frames_list) + "\n];"
        js_content = JAVASCRIPT_STRUCTURE % (svg_var, self.filename_base, vars_js, frames_js, self.filename_base)
        os.makedirs('media/svg_animations', exist_ok=True)
        if hasattr(self, "interactive_js"):
            js_content += "\n" + self.interactive_js
        with open(self.js_filename, "w") as f:
            f.write(js_content)
        with open(self.html_filename, "w") as f:
            f.write(self.html)
