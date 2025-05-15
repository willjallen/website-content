from manim import *
from manim_mobject_svg import *
from svgpathtools import svg2paths, parse_path
import itertools
import os
import re
import math # Added for detect_circle_from_path
import numpy as np # ADDED


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
var ready = true;
var timeouts = [];
var %s = document.getElementById("%s");
%s // Placeholder for global element variable declarations (e.g., var el0, el1, ...)
function render%s() {
    if (!ready) {
        for (var i=0; i<timeouts.length; i++) {
            clearTimeout(timeouts[i]);
        }
        while(timeouts.length > 0) {
            timeouts.pop();
        }
    }
    ready = false;
    rendered = false;
%s
    setTimeout(function() {
        ready = true;
        rendered = true;
    }, %f)
}"""


JAVASCRIPT_UPDATE_STRUCTURE = """    timeouts.push(setTimeout(function() {
        %s.replaceChildren();
        %s
    }, %f))"""


JAVASCRIPT_UPDATE_STRUCTURE_OPTIMIZED = """    timeouts.push(setTimeout(function() {
        %s
    }, %f))"""


JAVASCRIPT_INTERACTIVE_STRUCTURE = """var combsDict = {%s};
var comb = [%s];
function update(i, val) {
if (!rendered) {
    return
}
var keys = Object.keys(combsDict);
var ithElements = [];
for (let arr of keys) {
    if (Array.isArray(arr[i])) {   
        ithElements.push(arr[i]);
    }
    else {
        ithElements.push(arr);
    }
}
var x = val;
var closest = ithElements.sort( (a, b) => Math.abs(x - a) - Math.abs(x - b))[0];
comb[i] = closest;
combsDict[comb]();
}
"""


"""
Optimizations:

In general, our effort is to reduce the size of the js file and number of operations we do on the DOM.
Currently, the js file can get up to 1 GB in size, and the browser chugs at 15 fps trying to render it.
This is because there is a lot of redundant operation in the update loop.

So, we have the following plan:

- Update loop will only record the attributes dict, not write to the js file
- For each attributes object, we will hash it and assign it a (short as possible) unique name
- When we write to the js file, we will not delete and recreate *all* children with .replaceChildren()
- Instead, we will always keep as many children as there would otherwise be, and only update the attributes that have changed.
- For attributes that have changed, we will attempt to take a diff of the old and new attributes and only update the accordingly.
  - I say 'attempt' because we have no way of tagging the attributes objects from frame to frame, and moreover attributes can be added and removed per frame.
  - So instead we will do a best effort to match with whichever object has the most similar attributes.
    - Consider this scenario: on frame 4 we may have 12 children, and on frame 5 we may have 13 children
    - Furthermore, it's not the case that only 1 child was added. In fact 3 children were added and 2 children were removed.
    - So we will have to "shuffle" the children around in terms of what their update function is.
    - Again, the goal is to reduce the total number of operations we do on the DOM.
"""

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
        self.js_updates = ""
        self.frames_data = []
        self.continue_updating = True
        self.original_frame_width = self.scene.camera.frame_width
        self.original_frame_height = self.scene.camera.frame_height
        # For finish() method state, if needed across calls or for clarity
        # self.previous_attributes_map = {} 
        # self.previous_element_tags_map = {}
        self.scene.add_updater(self.updater)
    
    def _detect_circle_from_path(self, d: str, tol: float = 1e-2):
        """Return (cx, cy, r) if the SVG path string `d` is (approximately) a circle.
        This method uses a least-squares fit on sample points from the path.
        tol - absolute error in coordinate units for verifying points against the circle.
        """
        if not d:
            return None

        try:
            # svgpathtools.parse_path can handle complex SVG path strings
            path = parse_path(d)
        except Exception:  # Broad exception for any parsing errors
            return None

        if len(path) == 0:  # Path has no segments
            return None

        # A circle should be a single, closed contour.
        # Using a tighter tolerance for structural checks like closedness.
        # Max with 1e-7 avoids issues if tol is extremely small.
        closed_check_tol = max(tol * 0.01, 1e-7)
        if not path.iscontinuous() or not path.isclosed():
            return None

        # Collect a set of unique sample points from the path (complex numbers).
        sampled_points_complex = set()
        for segment in path:
            # Ensure segments are well-formed and have standard attributes
            if hasattr(segment, 'start') and hasattr(segment, 'point') and hasattr(segment, 'end'):
                 sampled_points_complex.add(segment.start)
                 sampled_points_complex.add(segment.point(0.5)) # Midpoint
                 sampled_points_complex.add(segment.end)
            else: # Path contains non-standard segments
                 return None


        if len(sampled_points_complex) < 3:  # Need at least 3 unique points for a circle fit.
            return None
        
        unique_points_list = list(sampled_points_complex)

        # Least-squares circle fit (Kåsa method / algebraic approach).
        # Solves for A, B, C in: x^2 + y^2 + A*x + B*y + C = 0
        coords = np.array([(p.real, p.imag) for p in unique_points_list])
        x_coords = coords[:, 0]
        y_coords = coords[:, 1]

        M_matrix = np.vstack([x_coords, y_coords, np.ones(len(unique_points_list))]).T
        P_vector = -(x_coords**2 + y_coords**2)

        try:
            params, _, rank, _ = np.linalg.lstsq(M_matrix, P_vector, rcond=None)
        except np.linalg.LinAlgError:
            return None  # LSQ solve failed

        if rank < 3: # Points are likely collinear or otherwise degenerate
            return None

        A_fit, B_fit, C_fit = params[0], params[1], params[2]

        cx = -A_fit / 2.0
        cy = -B_fit / 2.0
        r_squared = (A_fit**2 + B_fit**2) / 4.0 - C_fit

        # Radius check
        # Using a small epsilon (e.g., 1e-9 or tol^2) to avoid issues with floating point arithmetic
        if r_squared <= max(tol * tol * 0.01, 1e-9): 
            return None
        
        r = math.sqrt(r_squared)

        # Circle should not be excessively small (e.g. smaller than tolerance itself)
        if r < tol / 2.0 : 
            return None

        # Verification 1: All unique sampled points must lie on the fitted circle within tolerance.
        for p_complex in unique_points_list:
            dist_from_center = math.hypot(p_complex.real - cx, p_complex.imag - cy)
            if abs(dist_from_center - r) > tol:
                return None
        
        # Verification 2: Path length consistency.
        try:
            path_length_error_tol = max(tol * 0.1, 1e-7)
            path_actual_length = path.length(error=path_length_error_tol) 
        except Exception: 
            return None # path.length() computation failed

        expected_circumference = 2 * math.pi * r
        
        # Tolerance for path length: allows for Bezier approximations.
        # This might need tuning based on how paths are generated.
        length_relative_tolerance = 0.15 # 15% relative deviation
        length_absolute_tolerance = tol * 10 # Absolute deviation related to tol
        
        allowed_length_deviation = max(length_absolute_tolerance, length_relative_tolerance * r)

        if abs(path_actual_length - expected_circumference) > allowed_length_deviation:
            return None

        return cx, cy, r

    def _round_attribute_value(self, key: str, value_str: str, precision: int = 2) -> str:
        if not isinstance(value_str, str):
            return value_str # Should generally be a string from svg2paths attributes

        if key == 'd':
            # Simpler rounding for path data: find numbers and round them
            def round_d_match(match):
                try:
                    num = float(match.group(0))
                    return str(round(num, precision))
                except ValueError:
                    return match.group(0) # Should not happen with this regex
            try:
                return re.sub(r"[+-]?\d*\.?\d+([eE][+-]?\d+)?", round_d_match, value_str)
            except Exception:
                 return value_str
        
        simple_numeric_keys = ['fill-opacity', 'stroke-opacity', 'stroke-width', 'opacity', 'stroke-miterlimit', 'cx', 'cy', 'r']
        if key in simple_numeric_keys:
            try:
                val_float = float(value_str)
                # For small fractional values, try to maintain some significant digits
                if 0 < abs(val_float) < 1:
                    # Count leading zeros after decimal point for small positive numbers
                    s_val = str(val_float)
                    if '.' in s_val:
                        decimals = s_val.split('.', 1)[1]
                        leading_zeros = 0
                        for char_digit in decimals:
                            if char_digit == '0':
                                leading_zeros += 1
                            else:
                                break
                        # Aim for 2 significant digits after leading zeros
                        effective_precision = leading_zeros + 2 
                        return str(round(val_float, effective_precision))
                return str(round(val_float, precision))
            except ValueError:
                return value_str # e.g., if value is "inherit"

        if value_str.startswith("rgb(") or value_str.startswith("rgba("):
            is_rgba = value_str.startswith("rgba(")
            prefix = "rgba(" if is_rgba else "rgb("
            
            try:
                content = value_str[len(prefix):-1]
                parts_str_list = content.split(',')
                new_parts = []

                for i, part_s in enumerate(parts_str_list):
                    part_s = part_s.strip()
                    is_alpha_channel = is_rgba and i == 3

                    if part_s.endswith('%'):
                        num_str = part_s[:-1]
                        try:
                            num = float(num_str)
                            rounded_val_str = str(round(num, precision))
                            new_parts.append(rounded_val_str + '%')
                        except ValueError:
                            new_parts.append(part_s) # Unchanged if not a valid number
                    else: # Direct number
                        try:
                            num = float(part_s)
                            current_val_precision = 0 if not is_alpha_channel else precision
                            rounded_num = round(num, current_val_precision)
                            
                            # For alpha, if it rounds to 0 but wasn't 0, try more precision
                            if is_alpha_channel and rounded_num == 0 and num != 0:
                                check_precision = precision + 1
                                while round(num, check_precision) == 0 and check_precision < 10:
                                    check_precision += 1
                                rounded_num = round(num, check_precision)

                            if not is_alpha_channel and current_val_precision == 0:
                                new_parts.append(str(int(rounded_num)))
                            else:
                                new_parts.append(str(rounded_num))
                        except ValueError:
                            new_parts.append(part_s) # Unchanged
                
                return prefix + ", ".join(new_parts) + ")"
            except Exception: 
                return value_str # Fallback in case of unexpected format or error

        return value_str # Default: return original value
    
    def _escape_js_string(self, value: str) -> str:
        # Helper to escape strings for JS literals
        value = value.replace('\\', '\\\\')  # Escape backslashes
        value = value.replace("'", "\'")    # Escape single quotes
        value = value.replace('\n', '\\n')  # Escape newlines
        return value
    
    def updater(self, dt):
        if self.continue_updating is False:
            return
        
        current_frame_data = {}
        svg_filename = self.filename_base + str(self.current_index) + ".svg"
        self.vmobject.to_svg(svg_filename)
        
        _, attributes_from_svg = svg2paths(svg_filename)
        processed_attributes_list = []
        for attr_dict_original in attributes_from_svg:
            # Create a new dict for processed attributes for this element
            current_element_processed_attrs = {}
            
            # Handle 'd' attribute first for potential circle conversion
            d_path_value = None
            if 'd' in attr_dict_original:
                # Ensure d_path_value is a string for processing
                d_path_value_raw = attr_dict_original['d']
                d_path_value = str(d_path_value_raw) if not isinstance(d_path_value_raw, str) else d_path_value_raw
                
                circle_params = self._detect_circle_from_path(d_path_value)
                if circle_params:
                    cx, cy, r = circle_params
                    current_element_processed_attrs['_shape_type'] = 'circle'
                    # Round and store circle parameters
                    current_element_processed_attrs['cx'] = self._round_attribute_value('cx', str(cx), precision=2)
                    current_element_processed_attrs['cy'] = self._round_attribute_value('cy', str(cy), precision=2)
                    current_element_processed_attrs['r'] = self._round_attribute_value('r', str(r), precision=2)
                else:
                    # It's a path, not a circle
                    current_element_processed_attrs['_shape_type'] = 'path'
                    current_element_processed_attrs['d'] = self._round_attribute_value('d', d_path_value) # Round the path data
            else:
                # Not a path element from svg2paths or 'd' is missing. Default to 'path' or handle as other type.
                # Assuming svg2paths always gives 'd' for its elements. If not, this logic might need adjustment.
                # For now, if no 'd', it's not a candidate for circle conversion from path.
                # We'll assume other attributes define it, and it's not a 'path' in the sense we optimize.
                # To be safe, let's assign a generic type or let it pass through.
                # If it's not a path, it won't have 'd' for removal/addition logic.
                # However, all elements from svg2paths should be paths.
                 pass # Or assign a default _shape_type if necessary, e.g., 'unknown'

            # Process and round all other attributes from the original dictionary
            for k, v in attr_dict_original.items():
                if k == 'd': # Already handled (or skipped if became circle)
                    continue
                
                v_str = str(v) if not isinstance(v, str) else v
                current_element_processed_attrs[k] = self._round_attribute_value(k, v_str)

            # Ensure _shape_type is set if not already (e.g. if 'd' was missing but we still process other attrs)
            if '_shape_type' not in current_element_processed_attrs and 'd' not in attr_dict_original:
                # This case implies it's not a standard path from svg2paths that we are used to.
                # For safety in `finish`, ensure `_shape_type` exists. Default to 'path' if unsure,
                # or a more specific type if identifiable.
                # Given that `svg2paths` is used, this branch is unlikely.
                # If it's truly not a path, the diffing logic in `finish` might misinterpret it.
                # However, the problem focuses on paths becoming circles.
                 current_element_processed_attrs['_shape_type'] = 'path' # Fallback for safety

            processed_attributes_list.append(current_element_processed_attrs)
        current_frame_data["attributes"] = processed_attributes_list
        
        bg_color_rgba = color_to_int_rgba(self.scene.camera.background_color, self.scene.camera.background_opacity)
        bg_color_rgba[-1] = bg_color_rgba[-1] / 255
        bg_color_str_parts = [str(par) for par in bg_color_rgba]
        current_frame_data["background_color_str"] = f"rgb({', '.join(bg_color_str_parts)})"
        
        current_frame_data["viewBox_str_array"] = None # Default to None
        if isinstance(self.scene, MovingCameraScene):
            frame = self.scene.camera.frame
            pixel_width = self.scene.camera.pixel_width * self.scene.camera.frame_width / self.original_frame_width
            pixel_height = self.scene.camera.pixel_height * self.scene.camera.frame_height / self.original_frame_height
            frame_center = frame.get_corner(UL)
            pixel_center = frame_center * self.scene.camera.pixel_width / self.original_frame_width
            pixel_center += self.scene.camera.pixel_width / 2 * RIGHT + self.scene.camera.pixel_height / 2 * DOWN
            pixel_center[1] = -pixel_center[1]
            pixel_center = pixel_center[:2]
            arr = [*pixel_center, pixel_width, pixel_height]
            current_frame_data["viewBox_str_array"] = [str(p) for p in arr]
            
        current_frame_data["time"] = self.scene.renderer.time
        self.frames_data.append(current_frame_data)
        
        self.current_index += 1
        os.remove(svg_filename)
    
    def update_html(self):
        bg_color = color_to_int_rgba(
            self.scene.camera.background_color,
            self.scene.camera.background_opacity
        )
        bg_color[-1] = bg_color[-1] / 255
        bg_color = [str(c) for c in bg_color]
        bg_color = f"rgb({', '.join(bg_color)})"
        if self.basic_html is False:
            self.html = HTML_STRUCTURE % (
                self.filename_base,
                self.filename_base,
                self.width,
                self.scene.camera.pixel_width,
                self.scene.camera.pixel_height,
                bg_color,
                self.final_html_body,
                os.path.basename(self.js_filename)
            )
        else:
            self.html = BASIC_HTML_STRUCTURE % (
                self.filename_base,
                self.width,
                self.scene.camera.pixel_width,
                self.scene.camera.pixel_height,
                bg_color
            )
    
    def finish(self):
        self.scene.remove_updater(self.updater)
        if not hasattr(self, "last_t"):
            if self.frames_data:
                self.last_t = self.frames_data[-1]["time"]
            else:
                self.last_t = self.scene.renderer.time

        svg_container_var_name = self.filename_base.lower()

        max_paths_needed = 0
        max_circles_needed = 0
        if self.frames_data:
            for frame_data_check in self.frames_data:
                current_frame_paths = 0
                current_frame_circles = 0
                for attr_dict in frame_data_check["attributes"]:
                    if attr_dict.get('_shape_type') == 'circle':
                        current_frame_circles += 1
                    else:
                        current_frame_paths += 1
                max_paths_needed = max(max_paths_needed, current_frame_paths)
                max_circles_needed = max(max_circles_needed, current_frame_circles)

        global_el_vars_js = "    // Path elements\n"
        for i in range(max_paths_needed):
            global_el_vars_js += f"    var p_el{i};\n"
        global_el_vars_js += "    // Circle elements\n"
        for i in range(max_circles_needed):
            global_el_vars_js += f"    var c_el{i};\n"

        self.js_updates = ""
        previous_path_attributes_list = []
        previous_circle_attributes_list = []
        
        # Track visibility state to optimize .style.display changes
        path_element_is_hidden = [False] * max_paths_needed
        circle_element_is_hidden = [False] * max_circles_needed
        
        previous_background_color_str = None
        previous_viewBox_str_array = None

        for frame_index, frame_data in enumerate(self.frames_data):
            current_attributes_list_from_frame = frame_data["attributes"]
            time = frame_data["time"]
            viewBox_str_array = frame_data["viewBox_str_array"]
            background_color_str = frame_data["background_color_str"]

            frame_js_changes = ""

            current_frame_path_attrs_dicts = []
            current_frame_circle_attrs_dicts = []
            for attr_dict in current_attributes_list_from_frame:
                processed_attr_dict = {k: v for k, v in attr_dict.items() if k != '_shape_type'}
                if attr_dict.get('_shape_type') == 'circle':
                    current_frame_circle_attrs_dicts.append(processed_attr_dict)
                else:
                    current_frame_path_attrs_dicts.append(processed_attr_dict)

            if frame_index == 0:
                frame_js_changes += f"        {svg_container_var_name}.replaceChildren();\n"
                for i in range(max_paths_needed):
                    frame_js_changes += f"        p_el{i} = document.createElementNS('http://www.w3.org/2000/svg', 'path');\n"
                    frame_js_changes += f"        {svg_container_var_name}.appendChild(p_el{i});\n"
                for i in range(max_circles_needed):
                    frame_js_changes += f"        c_el{i} = document.createElementNS('http://www.w3.org/2000/svg', 'circle');\n"
                    frame_js_changes += f"        {svg_container_var_name}.appendChild(c_el{i});\n"
                if max_paths_needed > 0 or max_circles_needed > 0:
                    frame_js_changes += "        // End of initial element creation\n"

            for i in range(max_paths_needed):
                el_var_name = f"p_el{i}"
                if i < len(current_frame_path_attrs_dicts):
                    current_attrs_for_el = current_frame_path_attrs_dicts[i]
                    prev_attrs_for_el = previous_path_attributes_list[i] if i < len(previous_path_attributes_list) else {}
                    for k, v_curr_str in current_attrs_for_el.items():
                        v_prev_str = prev_attrs_for_el.get(k)
                        if str(v_curr_str) != str(v_prev_str):
                            escaped_v_curr = self._escape_js_string(str(v_curr_str))
                            frame_js_changes += f"       {el_var_name}.setAttribute('{k}', '{escaped_v_curr}');\n"
                    for k_prev in prev_attrs_for_el:
                        if k_prev not in current_attrs_for_el:
                            frame_js_changes += f"       {el_var_name}.removeAttribute('{k_prev}');\n"
                    if path_element_is_hidden[i]:
                        frame_js_changes += f"       {el_var_name}.style.display = '';\n"
                        path_element_is_hidden[i] = False
                else:
                    if not path_element_is_hidden[i]:
                        frame_js_changes += f"       {el_var_name}.style.display = 'none';\n"
                        path_element_is_hidden[i] = True

            for i in range(max_circles_needed):
                el_var_name = f"c_el{i}"
                if i < len(current_frame_circle_attrs_dicts):
                    current_attrs_for_el = current_frame_circle_attrs_dicts[i]
                    prev_attrs_for_el = previous_circle_attributes_list[i] if i < len(previous_circle_attributes_list) else {}
                    for k, v_curr_str in current_attrs_for_el.items():
                        v_prev_str = prev_attrs_for_el.get(k)
                        if str(v_curr_str) != str(v_prev_str):
                            escaped_v_curr = self._escape_js_string(str(v_curr_str))
                            frame_js_changes += f"       {el_var_name}.setAttribute('{k}', '{escaped_v_curr}');\n"
                    for k_prev in prev_attrs_for_el:
                        if k_prev not in current_attrs_for_el:
                            frame_js_changes += f"       {el_var_name}.removeAttribute('{k_prev}');\n"
                    if circle_element_is_hidden[i]:
                        frame_js_changes += f"       {el_var_name}.style.display = '';\n"
                        circle_element_is_hidden[i] = False
                else:
                    if not circle_element_is_hidden[i]:
                        frame_js_changes += f"       {el_var_name}.style.display = 'none';\n"
                        circle_element_is_hidden[i] = True
            
            if background_color_str != previous_background_color_str:
                frame_js_changes += f"     {svg_container_var_name}.style.backgroundColor = '{background_color_str}';\n"
                previous_background_color_str = background_color_str

            if viewBox_str_array != previous_viewBox_str_array:
                if viewBox_str_array is not None:
                    viewBox_value = ' '.join(viewBox_str_array)
                    frame_js_changes += f"     {svg_container_var_name}.setAttribute('viewBox', '{viewBox_value}');\n"
                previous_viewBox_str_array = viewBox_str_array

            if frame_js_changes.strip():
                self.js_updates += JAVASCRIPT_UPDATE_STRUCTURE_OPTIMIZED % (
                    frame_js_changes.rstrip('\n'),
                    1000 * time
                )
                self.js_updates += "\n"
            
            previous_path_attributes_list = [dict(attrs) for attrs in current_frame_path_attrs_dicts]
            previous_circle_attributes_list = [dict(attrs) for attrs in current_frame_circle_attrs_dicts]

        self.js_updates = self.js_updates.removesuffix("\n")
        
        js_content = JAVASCRIPT_STRUCTURE % (
            self.filename_base.lower(),
            self.filename_base,
            global_el_vars_js,
            self.filename_base,
            self.js_updates,
            1000 * self.last_t
        )
        
        os.makedirs('media/svg_animations', exist_ok=True)
        
        if hasattr(self, "interactive_js"):
            js_content += f"\n{self.interactive_js}"
        with open(self.js_filename, "w") as f:
            f.write(js_content)
        with open(self.html_filename, "w") as f:
            f.write(self.html)