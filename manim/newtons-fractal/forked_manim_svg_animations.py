from manim import *
from manim_mobject_svg import *
from svgpathtools import svg2paths
import itertools
import os


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
        %s // JavaScript commands for this frame
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
        self.html_filename = self.filename_base + ".html"
        self.js_filename = self.filename_base + ".js"
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
        
        _, attributes = svg2paths(svg_filename)
        current_frame_data["attributes"] = attributes
        
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
                self.js_filename
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

        for frame_data in self.frames_data:
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
            if len(current_attributes_list) > max_elements_ever_active_in_dom:
                max_elements_ever_active_in_dom = len(current_attributes_list)
            elif len(previous_attributes_list) > max_elements_ever_active_in_dom: # Handles cases where elements are removed
                 max_elements_ever_active_in_dom = len(previous_attributes_list)

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
                    # Element el_i is inactive (it existed before or is within max_elements_ever_active_in_dom but not in this frame's active list)
                    if i < max_elements_initialized_in_js: # Only hide if it was actually initialized
                        frame_js_changes += f"       {el_var_name}.style.display = 'none';\n"
                        current_frame_newly_hidden_indices.add(i)

            frame_js_changes += f"     {svg_container_var_name}.style.backgroundColor = '{background_color_str}';\n"

            if viewBox_str_array:
                viewBox_value = ' '.join(viewBox_str_array)
                frame_js_changes += f"     {svg_container_var_name}.setAttribute('viewBox', '{viewBox_value}');\n"

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
            global_el_vars_js, # For global el declarations
            self.filename_base,
            self.js_updates,
            1000 * self.last_t
        )
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
