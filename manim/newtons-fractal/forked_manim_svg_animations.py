from manim import *
from manim_mobject_svg import *
from svgpathtools import svg2paths
import itertools
import os
import re


HTML_STRUCTURE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>%s</title>
</head>
<body>
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
        self.scene.add_updater(self.updater)
    
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
        
        simple_numeric_keys = ['fill-opacity', 'stroke-opacity', 'stroke-width', 'opacity', 'stroke-miterlimit']
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
        for attr_dict in attributes_from_svg:
            rounded_attr_dict = {}
            for k, v in attr_dict.items():
                # Ensure value is a string before passing to _round_attribute_value, as svg2paths might return non-strings for some attributes
                v_str = str(v) if not isinstance(v, str) else v
                rounded_attr_dict[k] = self._round_attribute_value(k, v_str)
            processed_attributes_list.append(rounded_attr_dict)
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

        self.js_updates = ""
        svg_container_var_name = self.filename_base.lower()

        # Determine the overall maximum number of elements needed
        overall_max_elements = 0
        if self.frames_data:
            for frame_data_check in self.frames_data:
                overall_max_elements = max(overall_max_elements, len(frame_data_check["attributes"]))
        
        global_el_vars_js = ""
        for i in range(overall_max_elements):
            global_el_vars_js += f"    var el{i};\n"

        previous_attributes_list = []
        max_elements_ever_active_in_dom = 0 # Tracks highest index an element has occupied for display:none logic
        max_elements_initialized_in_js = 0  # Tracks elements for which create/append has been called
        previously_hidden_indices = set()
        previous_background_color_str = None
        previous_viewBox_str_array = None

        for frame_index, frame_data in enumerate(self.frames_data):
            current_attributes_list = frame_data["attributes"]
            time = frame_data["time"]
            viewBox_str_array = frame_data["viewBox_str_array"]
            background_color_str = frame_data["background_color_str"]

            frame_js_changes = ""
            current_frame_newly_hidden_indices = set()

            # Initialize and append new elements if needed
            if len(current_attributes_list) > max_elements_initialized_in_js:
                for i in range(max_elements_initialized_in_js, len(current_attributes_list)):
                    el_var_name = f"el{i}"
                    frame_js_changes += f"        {el_var_name} = document.createElementNS('http://www.w3.org/2000/svg', 'path');\n"
                    frame_js_changes += f"        {svg_container_var_name}.appendChild({el_var_name});\n"
                max_elements_initialized_in_js = len(current_attributes_list)
            
            # Update max_elements_ever_active_in_dom for display:none logic
            current_len = len(current_attributes_list)
            prev_len = len(previous_attributes_list)
            if current_len > max_elements_ever_active_in_dom:
                max_elements_ever_active_in_dom = current_len
            if prev_len > max_elements_ever_active_in_dom: # Check previous_attributes_list as well, as elements might have been removed
                max_elements_ever_active_in_dom = prev_len

            # Attribute diffing and updates
            for i in range(max_elements_ever_active_in_dom):
                el_var_name = f"el{i}"
                if i < len(current_attributes_list):
                    # Element el_i is active in this frame
                    current_attr_dict = current_attributes_list[i]
                    prev_attr_dict = previous_attributes_list[i] if i < len(previous_attributes_list) else {}

                    for k, v_current in current_attr_dict.items():
                        v_prev = prev_attr_dict.get(k)
                        if v_current != v_prev:
                            escaped_v_current = self._escape_js_string(v_current)
                            frame_js_changes += f"       {el_var_name}.setAttribute('{k}', '{escaped_v_current}');\n"
                    
                    for k_prev in prev_attr_dict:
                        if k_prev not in current_attr_dict:
                            frame_js_changes += f"       {el_var_name}.removeAttribute('{k_prev}');\n"
                    
                    if i in previously_hidden_indices: # Element was hidden, now active
                        frame_js_changes += f"       {el_var_name}.style.display = '';\n"
                else:
                    # Element el_i is inactive
                    # Only hide if it was initialized and was not already hidden in the previous frame state
                    if i < max_elements_initialized_in_js and i not in previously_hidden_indices:
                        frame_js_changes += f"       {el_var_name}.style.display = 'none';\n"
                        current_frame_newly_hidden_indices.add(i)
                    elif i < max_elements_initialized_in_js and i in previously_hidden_indices:
                        # It was already hidden, ensure it's part of the current hidden set if it remains hidden
                        current_frame_newly_hidden_indices.add(i)

            # Update background color only if it changed
            if background_color_str != previous_background_color_str:
                frame_js_changes += f"     {svg_container_var_name}.style.backgroundColor = '{background_color_str}';\n"
                previous_background_color_str = background_color_str

            # Update viewBox only if it changed
            if viewBox_str_array != previous_viewBox_str_array:
                if viewBox_str_array is not None: # Ensure it's not None before joining, if it became null
                    viewBox_value = ' '.join(viewBox_str_array)
                    frame_js_changes += f"     {svg_container_var_name}.setAttribute('viewBox', '{viewBox_value}');\n"
                else: 
                    # If current is None but previous wasn't, we might need to remove or reset it if applicable.
                    # For now, we assume setAttribute handles null by not changing or removing.
                    # If specific removal behavior is needed, it can be added here.
                    pass 
                previous_viewBox_str_array = viewBox_str_array

            # Add replaceChildren() for the very first frame to clear previous looped content
            if frame_index == 0:
                frame_js_changes = f"        {svg_container_var_name}.replaceChildren();\n" + frame_js_changes

            # Only add a timeout if there are actual changes for this frame
            if frame_js_changes.strip():
                self.js_updates += JAVASCRIPT_UPDATE_STRUCTURE_OPTIMIZED % (
                    frame_js_changes.rstrip('\n'),
                    1000 * time
                )
                self.js_updates += "\n"
            previous_attributes_list = current_attributes_list
            previously_hidden_indices = current_frame_newly_hidden_indices

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
    
    def start_interactive(
        self,
        value_trackers: list[ValueTracker],
        linspaces: list[np.ndarray],
        animate_this=True
    ):
        if animate_this is False:
            self.continue_updating = False
            self.last_t = self.scene.renderer.time
        print("This process can be slow, please wait!")
        self.interactive_js = ""
        filename = "update.svg"
        combs = itertools.product(*linspaces)
        combs_dict = ""
        comb_now = ", ".join([str(v.get_value()) for v in value_trackers])
        for comb in combs:
            for vt, val in zip(value_trackers, comb):
                self.scene.wait(1/self.scene.camera.frame_rate)
                vt.set_value(val)
            self.vmobject.to_svg(filename)
            html_el_creations = f"{self.filename_base.lower()}.replaceChildren();\n"
            _, attributes = svg2paths(filename)
            i = 0
            for attr in attributes:
                html_el_creation = f"        var el{i} = document.createElementNS('http://www.w3.org/2000/svg', 'path');\n"            
                for k, v in attr.items():
                    html_el_creation += f"       el{i}.setAttribute('{k}', '{v}');\n"
                html_el_creation += f"       {self.filename_base.lower()}.appendChild(el{i});\n"
                html_el_creations += html_el_creation
                i += 1
            
            combs_dict += "[" + ", ".join([str(v) for v in comb]) + """]: () => {
                %s
            },
            """ % html_el_creations
        self.interactive_js += JAVASCRIPT_INTERACTIVE_STRUCTURE % (combs_dict, comb_now)
        os.remove(filename)
