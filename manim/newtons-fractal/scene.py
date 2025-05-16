from multiprocessing import freeze_support
from typing import List
import uuid
from manim import *
from forked_manim_svg_animations import *
from manim.utils.family import extract_mobject_family_members

def vg_add_tagged(vg: VGroup, mobjects: List[Mobject], debug_name: str = None):

    for mobject in mobjects:
        if not isinstance(mobject, Mobject):
            continue
        mobject.tagged_name = uuid.uuid4()
        child_mobjects = extract_mobject_family_members(
            mobject,
            only_those_with_points=True,
        )
        for child in child_mobjects:
            child.tagged_name = uuid.uuid4()
            if debug_name is not None:
                child.debug_name = debug_name
        vg.add(mobject)

# 1 
# Just the quintic graph
class Figure1(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        ax = Axes(
            x_range=[-2, 2, 1],
            y_range=[-4, 4, 1],
            tips=False,
            axis_config={"include_numbers": True},
        )

        graph = ax.plot(lambda x: x ** 5 - x - 1, x_range=[-2, 2], use_smoothing=True)

        vg = VGroup(ax, graph)
        parsed = HTMLParsedVMobject(vg, self)

        self.add(ax, graph)
        parsed.finish()
        
#  2 
# Quintic graph with points selected
class Figure2(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        ax = Axes(
            x_range=[-2, 2, 1],
            y_range=[-4, 4, 1],
            tips=False,
            axis_config={"include_numbers": True},
        )

        f = lambda x: x ** 5 - x - 1
        x_0 = 0.9
        
        graph = ax.plot(f, x_range=[-2, 2], use_smoothing=True)

        
        x_point = Dot(ax.coords_to_point(x_0, 0), color=RED)
        fx_point = Dot(ax.coords_to_point(x_0, f(x_0)), color=BLUE)
        
        
        line = ax.get_vertical_line(ax.coords_to_point(x_0, f(x_0)))
        # line.depth = -3
        
        x_text = Tex('$x_0$').next_to(x_point, UP)
        # x_text.depth = -1
        
        fx_text = Tex('$f(x_0)$').next_to(fx_point, DOWN)
        # fx_text.depth = -1
        
        vg = VGroup(ax, graph, line, x_text, fx_text, x_point, fx_point)
        parsed = HTMLParsedVMobject(vg, self)
        
        self.add(ax, graph, line, x_text, fx_text, x_point, fx_point)
        parsed.finish()
    
# 3 
# Quintic Graph with points selected and the tangent line shown for x_0
class Figure3(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        ax = Axes(
            x_range=[-2, 2, 1],
            y_range=[-4, 4, 1],
            tips=False,
            axis_config={"include_numbers": True},
        )



        f = lambda x: x ** 5 - x - 1
        fp = lambda x: 5*(x ** 4) - 1
        x_0 = 0.9

        fx_graph = ax.plot(f, x_range=[-2, 2], use_smoothing=True)

        
        x_point = Dot(ax.coords_to_point(x_0, 0), color=RED)
        fx_point = Dot(ax.coords_to_point(x_0, f(x_0)), color=BLUE)
        
        
        line = ax.get_vertical_line(ax.coords_to_point(x_0, f(x_0)))

        
        x_text = Tex('$x_0$').next_to(x_point, UP)

        
        fx_text = Tex('$f(x_0)$').next_to(fx_point, DOWN)
        
        # slopes = ax.get_secant_slope_group(
        #     x=x_0,
        #     graph=graph,
        #     dx=0.1,
        #     dx_label=None,
        #     dy_label=None,
        #     dx_line_color=None,
        #     dy_line_color=None,
        #     secant_line_length=16,
        #     secant_line_color=RED_D,
        # )
        
        t = lambda x: fp(x_0)*(x - x_0) + f(x_0)

        t_graph = ax.plot(t, x_range=[-2, 2], use_smoothing=True)
        t_graph.color = RED
        
        
        tx_text = Tex('$t(x_0)$').next_to(fx_point, RIGHT * 4)
        tx_text.color = RED
        
        vg = VGroup(ax, fx_graph, line, x_text, fx_text, t_graph, tx_text, x_point, fx_point)
        parsed = HTMLParsedVMobject(vg, self)

        self.add(ax, fx_graph, line, x_text, fx_text, t_graph, tx_text, x_point, fx_point)
        parsed.finish()
        
# 4
# Quintic Graph with points selected and the tangent line shown for x_0 and the tangent line intercept to the x-axis
class Figure4(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        ax = Axes(
            x_range=[-2, 2, 1],
            y_range=[-4, 4, 1],
            tips=False,
            axis_config={"include_numbers": True},
        )



        f = lambda x: x ** 5 - x - 1
        fp = lambda x: 5*(x ** 4) - 1
        x_0 = 0.9

        fx_graph = ax.plot(f, x_range=[-2, 2], use_smoothing=True)

        
        x_point = Dot(ax.coords_to_point(x_0, 0), color=RED)
        fx_point = Dot(ax.coords_to_point(x_0, f(x_0)), color=BLUE)
        
        
        line = ax.get_vertical_line(ax.coords_to_point(x_0, f(x_0)))

        
        x_text = Tex('$x_0$').next_to(x_point, UP)

        
        fx_text = Tex('$f(x_0)$').next_to(fx_point, DOWN)
        
        # slopes = ax.get_secant_slope_group(
        #     x=x_0,
        #     graph=graph,
        #     dx=0.1,
        #     dx_label=None,
        #     dy_label=None,
        #     dx_line_color=None,
        #     dy_line_color=None,
        #     secant_line_length=16,
        #     secant_line_color=RED_D,
        # )
        
        t = lambda x: fp(x_0)*(x - x_0) + f(x_0)

        t_graph = ax.plot(t, x_range=[-2, 2], use_smoothing=True)
        t_graph.color = RED
        
        
        tx_text = Tex('$t(x_0)$').next_to(fx_point, RIGHT * 4)
        tx_text.color = RED
       
        tx_intercept = Dot(ax.coords_to_point(x_0 - (f(x_0)/fp(x_0)),0))
        tx_intercept.color = GREEN
        
        tx_intercept_text = Tex('$x_1$').next_to(tx_intercept, np.array([0.0,0.8,0])) 
        tx_intercept_text.color = GREEN
        # tx_intercept_text.scale_to_fit_width(1.2)
        
        vg = VGroup(ax, fx_graph, line, x_text, fx_text, t_graph, tx_text, tx_intercept, x_point, fx_point, tx_intercept_text)
        parsed = HTMLParsedVMobject(vg, self)
        
        self.add(ax, fx_graph, line, x_text, fx_text, t_graph, tx_text, tx_intercept, x_point, fx_point, tx_intercept_text)
        # self.add(ax, fx_graph, line, t_graph, tx_intercept, x_point, fx_point, tx_intercept_text)
        parsed.finish()
    
# 5
# Animation of newtons method from start of figure 4
class Figure5(Scene):
    def construct(self):
        self.camera.background_color = BLACK
        ax = Axes(
            x_range=[-2, 2, 1],
            y_range=[-4, 4, 1],
            tips=False,
            axis_config={"include_numbers": True},
        )

        x_n_arr = []
        x_n_manim_arr = []

        f = lambda x: x ** 5 - x - 1
        fp = lambda x: 5*(x ** 4) - 1
        x_0 = 0.9
        x_n_arr.append(x_0)
        text_arr = []
        fx_arr = []
        
        fx_graph = ax.plot(f, x_range=[-2, 2], use_smoothing=True)
        
        x_point = Dot(ax.coords_to_point(x_0, 0), color=RED)
        x_n_manim_arr.append(x_point)
        
        fx_point = Dot(ax.coords_to_point(x_0, f(x_0)), color=BLUE)
        fx_arr.append(fx_point)
        
        line = ax.get_vertical_line(ax.coords_to_point(x_0, f(x_0)))
        x_text = Tex('$x_0$').next_to(x_point, UP)
        fx_text = Tex('$f(x_0)$').next_to(fx_point, DOWN)
        
        t = lambda x: fp(x_0)*(x - x_0) + f(x_0)

        t_graph = ax.plot(t, x_range=[-2, 2], use_smoothing=True)
        t_graph.color = RED
        
        
        tx_text = Tex('$t(x_0)$').next_to(fx_point, RIGHT * 4)
        tx_text.color = RED
       
        tx_intercept = Dot(ax.coords_to_point(x_0 - (f(x_0)/fp(x_0)),0))
        x_n_manim_arr.append(tx_intercept)
        tx_intercept.color = GREEN
        
        tx_intercept_text = Tex('$x_1$').next_to(tx_intercept, np.array([0.0,0.8,0])) 
        tx_intercept_text.color = GREEN
        text_arr.append(tx_intercept_text)
        
        self.vg = VGroup()
        parsed = HTMLParsedVMobject(self.vg, self)
        vg_add_tagged(self.vg, [ax, fx_graph, line, x_text, fx_text, t_graph, tx_text, tx_intercept, x_point, fx_point, tx_intercept_text])

        self.add(ax, fx_graph, line, x_text, fx_text, t_graph, tx_text, tx_intercept, x_point, fx_point, tx_intercept_text)
        
        self.wait()
        
        self.play(
            x_text.animate.set_opacity(0),
            fx_text.animate.set_opacity(0),
            line.animate.set_opacity(0),
            tx_text.animate.set_opacity(0),
            t_graph.animate.set_opacity(0)
            )
        
        self.vg.remove(x_text, fx_text, line, tx_text, t_graph)
        self.remove(x_text, fx_text, line, tx_text, t_graph)

        x_n = x_0 - f(x_0)/fp(x_0)
        x_n_arr.append(x_n)
        
        x_n_text = Tex('$x_ 1\\approx$ ' + f'{x_n:.4f}')
        x_n_text.color = GREEN
        x_n_text.to_corner(DR)
        vg_add_tagged(self.vg, [x_n_text])
        
        self.play(Create(x_n_text))
        
        for n in range(2, 5):
            
            x_point = Dot(ax.coords_to_point(x_n, 0), color=RED)
            line = ax.get_vertical_line(ax.coords_to_point(x_n, f(x_n)))
            vg_add_tagged(self.vg, [line])
            self.play(Create(line))

            fx_point = Dot(ax.coords_to_point(x_n, f(x_n)), color=BLUE)
            fx_arr.append(fx_point)
            vg_add_tagged(self.vg, [fx_point])
            self.play(Create(fx_point))
            
            t = lambda x: fp(x_n)*(x - x_n) + f(x_n)

            t_graph = ax.plot(t, x_range=[-2, 2], use_smoothing=True)
            t_graph.color = RED
            vg_add_tagged(self.vg, [t_graph])
            self.play(Create(t_graph))
            
            # Label for the tangent at the current x_n (which is x_{n-1} in sequence x_0, x_1, ...)
            tangent_label = Tex('$t(x_{'+str(n-1)+'})$').next_to(fx_point, RIGHT * 4)
            tangent_label.color = RED
            vg_add_tagged(self.vg, [tangent_label])
            self.play(Create(tangent_label))
        
            tx_intercept = Dot(ax.coords_to_point(x_n - (f(x_n)/fp(x_n)),0))
            tx_intercept.color = GREEN
            
            x_n = x_n - f(x_n)/fp(x_n)
            x_n_arr.append(x_n)
            
            new_x_n_text = Tex('$x_'+str(n)+'\\approx$ ' + f'{x_n:.4f}')
            new_x_n_text.color = GREEN
            new_x_n_text.to_corner(DR)

            x_n_manim_arr.append(tx_intercept)
            vg_add_tagged(self.vg, [new_x_n_text, tx_intercept])
            self.play(ReplacementTransform(x_n_text, new_x_n_text), Create(tx_intercept))
            self.vg.remove(x_n_text)
            x_n_text = new_x_n_text
            
            if(n == 2):
                tx_intercept_text = Tex('$x_'+str(n)+'$').next_to(tx_intercept, DOWN) 
                tx_intercept_text.color = GREEN
                text_arr.append(tx_intercept_text)
                vg_add_tagged(self.vg, [tx_intercept_text])
                self.play(Create(tx_intercept_text))
            
            self.play(FadeOut(t_graph), FadeOut(line), FadeOut(tangent_label))
            self.vg.remove(t_graph, line, tangent_label)

            if(n == 3):
                zoom_out_square = Rectangle(color=YELLOW)
                zoom_out_square.move_to(tx_intercept)
                vg_add_tagged(self.vg, [zoom_out_square])
                self.play(Create(zoom_out_square))
                
                old_ax = ax
                old_fx_graph = fx_graph

                new_ax = Axes(
                    x_range=[1.1, 1.3, 0.1],
                    y_range=[-0.2, 0.2, 0.1],
                    tips=False,
                    axis_config={"include_numbers": True},
                )
                new_fx_graph = new_ax.plot(f, x_range=[1.1, 1.3], use_smoothing=True)
                
                new_x_n_dots_for_vg = []
                x_n_transforms = []
                for i in range(len(x_n_arr)): # x_n_arr has x0,x1,x2,x3
                    old_dot = x_n_manim_arr[i]
                    new_dot = Dot(new_ax.coords_to_point(x_n_arr[i], 0), color=GREEN)
                    new_x_n_dots_for_vg.append(new_dot)
                    vg_add_tagged(self.vg, [new_dot])
                    x_n_transforms.append(ReplacementTransform(old_dot, new_dot))
                
                new_fx_dots_for_vg = []
                fx_transforms = []
                # fx_arr has f(x0), f(x1), f(x2). x_n_arr also has corresponding x0,x1,x2
                for i in range(len(fx_arr)): 
                    old_dot = fx_arr[i]
                    # new_fx_dot is f(x_n_arr[i]) on new_ax
                    new_dot = Dot(new_ax.coords_to_point(x_n_arr[i], f(x_n_arr[i])), color=BLUE)
                    new_fx_dots_for_vg.append(new_dot)
                    vg_add_tagged(self.vg, [new_dot])
                    fx_transforms.append(ReplacementTransform(old_dot, new_dot))
                    
                
                self.play(
                    ReplacementTransform(old_ax, new_ax), 
                    ReplacementTransform(old_fx_graph, new_fx_graph), 
                    ScaleInPlace(zoom_out_square, 8), 
                    *x_n_transforms, 
                    *fx_transforms
                )
                self.vg.remove(zoom_out_square)
                
                for dot in x_n_manim_arr: # These are the original dots
                    self.vg.remove(dot)
                for dot in fx_arr: # These are the original dots
                    self.vg.remove(dot)
                
                # Update references to the new mobjects
                ax = new_ax
                fx_graph = new_fx_graph
                x_n_manim_arr = new_x_n_dots_for_vg
                fx_arr = new_fx_dots_for_vg
        
        parsed.finish()
        
if __name__ == "__main__":
    freeze_support()
    with tempconfig(
        {
            "quality": "low_quality",
            "disable_caching": True,
            "frame_rate": 30,
            "dry_run": True,
            "pixel_height": 2160,
            "pixel_width": 3840,
            "background_color": BLACK,
            "background_opacity": 1
        }
    ):
        scene = Figure5()
        scene.render()

# 6
# New function
# Better code
class Figure6(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        
        f = lambda x : ((x ** (1/2)) if x >= 0 else -((-x) ** (1/2)))
        
        # Graph stuff
        x_range_graph = [-5, 5, 1]
        y_range_graph = [-4, 4, 1]
        
        x_range_function = [-5, 5, 0.01]
        
        graph_axes = Axes(
            x_range=x_range_graph,
            y_range=y_range_graph,
            tips=False,
            axis_config={"include_numbers": True},
        )
        
        
        function_graph = graph_axes.plot(f, x_range=x_range_function, use_smoothing=True)
        
        vg = VGroup(graph_axes, function_graph)
        parsed = HTMLParsedVMobject(vg, self)

        self.add(graph_axes, function_graph)
        parsed.finish()

            
# 7
# General form newtons method
class Figure7(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        
        f = lambda x : ((x ** (1/2)) if x >= 0 else -((-x) ** (1/2)))
        fp = lambda x : (((1/2) * (x ** (-1/2))) if x >= 0 else ((1/2) * (-x) ** (-1/2)))
        
        initial_guess_x0 = 1
        iterations = 4
        
        # Graph stuff
        x_range_graph = [-5, 5, 1]
        y_range_graph = [-4, 4, 1]
        
        x_range_function = [-5, 5, 0.01]
        
        graph_axes = Axes(
            x_range=x_range_graph,
            y_range=y_range_graph,
            tips=False,
            axis_config={"include_numbers": True},
        )
        
        
        function_graph = graph_axes.plot(f, x_range=x_range_function, use_smoothing=True)
        
        vg = VGroup(graph_axes, function_graph)
        parsed = HTMLParsedVMobject(vg, self)

        self.add(graph_axes, function_graph)
        
        x_n = initial_guess_x0
        fx_n = f(initial_guess_x0)
        
        x_n_arr = [initial_guess_x0]
        x_n_manim_obj_arr = []
        
        fx_n_arr = []
        fx_n_manim_obj_arr = []
        
        x_n_text = None
        
        # x_n_text.add_updater(lambda z : z._s)
        
        
        # Newton's method
        for n in range(0, iterations):
            
            # Display the current x_n
            x_n_point = Dot(graph_axes.coords_to_point(x_n, 0), color=RED)
            x_n_manim_obj_arr.append(x_n_point)
            self.play(Create(x_n_point))
            vg.add(x_n_point)
            
            if n == 0:
                x_n_text = Tex('$x_ 1\\approx$ ' + str(x_n))
                x_n_text.to_corner(DR)
                self.play(Create(x_n_text))
                vg.add(x_n_text)

            # Display fx_n
            fx_n_point = Dot(graph_axes.coords_to_point(x_n, f(x_n)), color=BLUE)
            fx_n_arr.append(fx_n_point) # This seems to be fx_n_manim_obj_arr based on naming pattern elsewhere
            x_n_to_fx_n_line = graph_axes.get_vertical_line(graph_axes.coords_to_point(x_n, f(x_n)))
            self.play(Create(x_n_to_fx_n_line))
            vg.add(x_n_to_fx_n_line)
            self.play(Create(fx_n_point))
            vg.add(fx_n_point)
            
            
            # Display tangent line
            tangent_line_x = lambda x: fp(x_n)*(x - x_n) + f(x_n)

            tangent_line_x_graph = graph_axes.plot(tangent_line_x, x_range=x_range_graph, use_smoothing=True)
            tangent_line_x_graph.color = RED
            self.play(Create(tangent_line_x_graph))
            vg.add(tangent_line_x_graph)
            
            # tx_text = Tex('$x_'+str(n)+'$').next_to(fx_point, RIGHT * 4)
            # tx_text.color = RED
            
            # Display the intercept
            tangent_line_x_intercept_point = Dot(graph_axes.coords_to_point(x_n - (f(x_n)/fp(x_n)),0))
            tangent_line_x_intercept_point.color = GREEN
            
            x_n = x_n - f(x_n)/fp(x_n)
            x_n_arr.append(x_n)
            
            new_x_n_text = Tex('$x_'+str(n)+'\\approx$ ' + str(x_n))
            new_x_n_text.to_corner(DR)
            
            self.play(ReplacementTransform(x_n_text, new_x_n_text), Create(tangent_line_x_intercept_point))
            vg.remove(x_n_text)
            vg.add(new_x_n_text, tangent_line_x_intercept_point)
            x_n_text = new_x_n_text
            
            fx_n = f(x_n)
            fx_n_arr.append(fx_n) # This seems to add a float, not a mobject. fx_n_manim_obj_arr might be intended for mobjects.
            
            self.play(
                x_n_point.animate.set_opacity(0),
                fx_n_point.animate.set_opacity(0),
                x_n_to_fx_n_line.animate.set_opacity(0),
                tangent_line_x_graph.animate.set_opacity(0),
            )
            vg.remove(x_n_point, fx_n_point, x_n_to_fx_n_line, tangent_line_x_graph)
                # tangent_line_x_intercept_point.animate.set_opacity(0), # This was commented out, if it fades, it should be removed from vg too.


            self.remove(x_n_point, fx_n_point, x_n_to_fx_n_line, tangent_line_x_graph)
        parsed.finish() # Moved to after the loop

# Complex plane
class Figure8(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        
        x_range_graph = (-2, 2, 1)
        y_range_graph = (-2, 2, 1)
        
        # x_range_function = [-5, 5, 0.01]
        
        plane = ComplexPlane(x_range=x_range_graph, y_range=y_range_graph).add_coordinates().scale(2)
        self.add(plane)
        
        d1 = Dot(plane.n2p(1 + 1j), color=YELLOW)
        d2 = Dot(plane.n2p(-1 - 1j), color=YELLOW)
        label1 = MathTex("1+i").next_to(d1, UR, 0.1)
        label2 = MathTex("-1-i").next_to(d2, UR, 0.1)
        self.add(
            d1,
            label1,
            d2,
            label2,
        )
        
        vg = VGroup(plane, d1, label1, d2, label2)
        parsed = HTMLParsedVMobject(vg, self)
        parsed.finish()
        
        
# Complex plane
# Addition and multiplication
class Figure9(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        
        x_range_graph = (-2, 2, 1)
        
        plane = ComplexPlane(x_range=x_range_graph, y_range=y_range_graph).add_coordinates().scale(2)
        self.add(plane)
        
        d1 = Dot(plane.n2p(1 + 1j), color=YELLOW)
        d2 = Dot(plane.n2p(-1 - 1j), color=YELLOW)
        label1 = MathTex("1+i").next_to(d1, UR, 0.1)
        label2 = MathTex("-1-i").next_to(d2, UR, 0.1)
        self.add(
            d1,
            label1,
            d2,
            label2,
        )
        
        vg = VGroup(plane, d1, label1, d2, label2)
        parsed = HTMLParsedVMobject(vg, self)
        
        d3 = Dot(plane.n2p(complex(1,1) + complex(-1,-1)), color=YELLOW)
        label3 = MathTex("(1+i) + (-1-i)").next_to(d3, UR, 0.1)
        self.play(Create(d3), Create(label3))
        vg.add(d3, label3)

        self.play(Wait(run_time=0.5))
        new_label3 = MathTex("0 + 0i").next_to(d3, UR, 0.1)
        self.play(ReplacementTransform(label3, new_label3))
        vg.remove(label3)
        vg.add(new_label3)

        self.play(Wait(run_time=0.5))

        d4 = Dot(plane.n2p(complex(1,1) * complex(-1,-1)), color=YELLOW)
        label4 = MathTex("(1+i) \\cdot (-1-i)").next_to(d4, UR, 0.1)
        
        self.play(Create(d4), Create(label4))
        vg.add(d4, label4)

        self.play(Wait(run_time=0.5))
        new_label4 = MathTex("0 - 2i").next_to(d4, UR, 0.1)
        self.play(ReplacementTransform(label4, new_label4))
        vg.remove(label4)
        vg.add(new_label4)

        self.play(Wait(run_time=2))
        parsed.finish()

            
# Complex plane w/ function applied
class Figure10(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        
        x_range_graph = (-2, 2, 1)
        y_range_graph = (-2, 2, 1)
        
        # x_range_function = [-5, 5, 0.01]
        
        f = lambda z : (z ** 3) - 1
        
        plane = ComplexPlane(x_range=x_range_graph, y_range=y_range_graph).add_coordinates().scale(2)
        self.add(plane)
        
        vg = VGroup(plane) # Initialize VGroup with the plane
        parsed = HTMLParsedVMobject(vg, self)

        dots = []
        # dots_trajectory = [] # This is unused
        
        for x in np.arange(-2, 2, 0.05):
            for y in np.arange(-2, 2, 0.05):
                dot = Dot(plane.n2p(complex(x,y)), color=YELLOW, radius=0.01) 
                self.add(dot) 
                vg.add(dot)
                dots.append(dot)
                
                dot.generate_target()
                dot.target.move_to(plane.n2p((complex(x,y) ** 3) - 1))

        
        animations = tuple(MoveToTarget(x, run_time=5) for x in dots)

        self.play(*animations)
        parsed.finish()
        
        
        # d1 = Dot(plane.n2p(2 + 1j), color=YELLOW)
        # d2 = Dot(plane.n2p(-3 - 2j), color=YELLOW)
        # label1 = MathTex("2+i").next_to(d1, UR, 0.1)
        # label2 = MathTex("-3-2i").next_to(d2, UR, 0.1)

# Newton's method with just one point on the complex plane
class Figure11(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        
        x_range_graph = (-2, 2, 1)
        y_range_graph = (-2, 2, 1)
        
        # x_range_function = [-5, 5, 0.01]
        
        f = lambda z : (z ** 3) - 1
        fp = lambda z : 3*(z ** 2)
        
        plane = ComplexPlane(x_range=x_range_graph, y_range=y_range_graph).add_coordinates().scale(2)
        # plane.set_color(GRAY)
        self.add(plane)
        
        dots = []

        coordinate = complex(1,1)
        dot = Dot(plane.n2p(coordinate), radius=0.1) 
        
        # dot_label = MathTex(str(float(f'{coordinate.real:.2f}')) + ' + ' + str(float(f'{coordinate.imag:.2f}')) + 'i').next_to(dot, UR, 0.1)
        # dot_label.set_color(BLACK)
                
        vg = VGroup(plane, dot) # Initial objects
        parsed = HTMLParsedVMobject(vg, self)

        self.play(Create(dot))
        
        # Newton's method
        for i in range(0, 6):
            coordinate = coordinate - f(coordinate)/fp(coordinate)

            dot.generate_target()
            # dot_label.generate_target()
            
            dot.target.move_to(plane.n2p(coordinate))
            
            # dot_label.target.next_to(plane.n2p(coordinate), UR, 0.1)
            
            # self.play(MoveToTarget(dot, run_time=2), MoveToTarget(dot_label, run_time = 2))
            self.play(MoveToTarget(dot, run_time=2))
            # dot and dot_label are already in vg, MoveToTarget updates them in place for SVG if targets are mobjects.
            
            # new_dot_label = MathTex(str(float(f'{coordinate.real:.2f}')) + ' + ' + str(float(f'{coordinate.imag:.2f}')) + 'i').next_to(dot, UR, 0.1)
            # self.play(ReplacementTransform(dot_label, new_dot_label))
            # vg.remove(dot_label)
            # vg.add(new_dot_label)
            # dot_label = new_dot_label
            
        self.play(Wait(run_time=2))
        parsed.finish()

# Complex plane w/ function applied to just one point at -1, 0
class Figure12(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        
        x_range_graph = (-2, 2, 1)
        y_range_graph = (-2, 2, 1)
        
        # x_range_function = [-5, 5, 0.01]
        
        f = lambda z : (z ** 3) - 1
        coordinate = complex(1,0)
        
        plane = ComplexPlane(x_range=x_range_graph, y_range=y_range_graph).add_coordinates().scale(2)
        self.add(plane)
        
        dots = []
        # dots_trajectory = []
        
        dot = Dot(plane.n2p(coordinate), color=YELLOW, radius=0.1) 
        # dots.append(dot)

        vg = VGroup(plane, dot) # Initialize with plane and initial dot
        parsed = HTMLParsedVMobject(vg, self)
        
        self.play(Create(dot))
        
        # animations = tuple(MoveToTarget(x, run_time=5) for x in dots)
        dot.generate_target()
        dot.target.move_to(plane.n2p(f(coordinate)))

        self.play(MoveToTarget(dot))
        self.play(Wait(run_time=2))
        parsed.finish()
        
        
        # d1 = Dot(plane.n2p(2 + 1j), color=YELLOW)
        # d2 = Dot(plane.n2p(-3 - 2j), color=YELLOW)
        # label1 = MathTex("2+i").next_to(d1, UR, 0.1)
        # label2 = MathTex("-3-2i").next_to(d2, UR, 0.1)
        
# Newton's method on a bunch of points
class Figure13(Scene):
    def construct(self):
        self.camera.background_color = WHITE
        
        x_range_graph = (-2, 2, 1)
        y_range_graph = (-2, 2, 1)
        
        # x_range_function = [-5, 5, 0.01]
        
        f = lambda z : (z ** 3) - 1
        fp = lambda z : 3*(z ** 2)
        
        plane = ComplexPlane(x_range=x_range_graph, y_range=y_range_graph).add_coordinates().scale(2)
        self.add(plane)
        
        vg = VGroup(plane) # Initialize with the plane
        parsed = HTMLParsedVMobject(vg, self)
        
        
        dots = []
        # dots_trajectory = [] # Unused
        
        for x in np.arange(-2, 2, 0.05):
            for y in np.arange(-2, 2, 0.05):
                dot = Dot(plane.n2p(complex(x,y)), color=YELLOW, radius=0.01) 
                dots.append([dot, complex(x,y)])
                self.add(dot)
                vg.add(dot) # Add dot to VGroup
        
        # Newton's method
        # 6 iterations
        for i in range(0, 8):
            for dot in dots:
                manim_dot = dot[0]
                
                dot_coordinate = dot[1]
                dot_coordinate = dot_coordinate - f(dot_coordinate)/fp(dot_coordinate)
                dot[1] = dot_coordinate
                
                manim_dot.generate_target()
                                
                manim_dot.target.move_to(plane.n2p(dot_coordinate))

            animations = tuple(MoveToTarget(x[0], run_time=5) for x in dots)
            self.play(*animations)
            # self.play(Wait(run_time=0.5))
            
        self.play(Wait(run_time=2))
        parsed.finish()
