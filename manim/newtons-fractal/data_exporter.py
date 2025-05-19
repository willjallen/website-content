import os
import struct
from typing import List

import itertools
import numpy as np
from manim import VGroup, VMobject, config
from manim.utils.family import extract_mobject_family_members

CTX_CONFIG_MARKER = b'CTX0'
FRAME_MARKER = b'FRAME'
VMO_MARKER = b'VMO'
VMO_SUBPATH_MARKER = b'VMO_SP'
VMO_SUBPATH_QUAD_MARKER = b'VMO_SP_QUAD'

LE = '<'  # little-endian
mgc = '4s'
i32 = 'i'
u32 = 'I'
f32 = 'f'


class ManimDataExporter:
    def __init__(self, data_file: os.path):
        os.makedirs(os.path.dirname(data_file), exist_ok=True)
        self._fh = open(data_file, "wb", buffering=1 << 20)
        self._emit_ctx_config()

    def _write(self, fmt, *vals):
        self._fh.write(struct.pack(LE + fmt, *vals))

    @staticmethod
    def _transform_points_pre_display(points: np.ndarray) -> np.ndarray:
        if not np.all(np.isfinite(points)):
            return np.zeros((1, 3))
        return points

    def _emit_ctx_config(self):
        self._write(mgc, b'CTXT')
        self._write(u32 + u32 + u32 + f32 + f32,
                    1,
                    config.pixel_width, config.pixel_height,
                    config.frame_width, config.frame_height
                     )

    def _emit_frame(self, _VMOcount):
        self._write(mgc, b'FRAM')
        self._write(u32, _VMOcount)

    def _emit_vmobject(self, vmo: VMobject):

        _stroke_width_background = vmo.get_stroke_width(True)
        _stroke_width = vmo.get_stroke_width(False)

        stroke_RGBAs_background = vmo.get_stroke_rgbas(True)
        _stroke_RGBAs_background_count = len(list(stroke_RGBAs_background))
        stroke_RGBAs = vmo.get_stroke_rgbas(False)
        _stroke_RGBAs_count = len(list(stroke_RGBAs))

        fill_RGBAs = vmo.get_fill_rgbas()
        _fill_RGBAs_count = len(list(fill_RGBAs))

        gradient_points = vmo.get_gradient_start_and_end_points()
        gradient_points = self._transform_points_pre_display(gradient_points)
        _gradient_x0, _gradient_y0, _gradient_x1, _gradient_y1 = (itertools.chain(*(p[:2] for p in gradient_points)))
        points = ManimDataExporter._transform_points_pre_display(vmo.points)
        subpaths = list(vmo.gen_subpaths_from_points_2d(points))
        _subpaths_count = len(subpaths)

        self._write(mgc, b'VMOB')
        self._write(u32, vmo.tagged_name)
        print(vmo.tagged_name)
        # Style
        self._write(f32, _stroke_width_background)
        self._write(f32, _stroke_width)
        self._write(u32, _stroke_RGBAs_background_count)
        self._write(u32, _stroke_RGBAs_count)
        self._write(u32, _fill_RGBAs_count)
        self._write(f32 + f32 + f32 + f32, _gradient_x0, _gradient_y0, _gradient_x1, _gradient_y1)
        self._write(u32, _subpaths_count)

        for _rgba in stroke_RGBAs_background:
            self._write(mgc, b'RGBA')
            self._write(f32 + f32 + f32 + f32, *_rgba)

        for _rgba in stroke_RGBAs:
            self._write(mgc, b'RGBA')
            self._write(f32 + f32 + f32 + f32, *_rgba)

        for _rgba in fill_RGBAs:
            self._write(mgc, b'RGBA')
            self._write(f32 + f32 + f32 + f32, *_rgba)

        # ctx.new_path()
        for subpath in vmo.gen_subpaths_from_points_2d(points):

            quads = list(vmo.gen_cubic_bezier_tuples_from_points(subpath))
            _quad_count = len(quads)
            _x, _y = subpath[0][:2]

            self._write(mgc, b'SUBP')
            self._write(f32 + f32, _x, _y)
            self._write(u32, _quad_count)

            # ctx.new_sub_path()
            # ctx.move_to(*subpath[0][:2])
            for _p0, p1, p2, p3 in quads:
                x1, y1 = p1[:2]
                x2, y2 = p2[:2]
                x3, y3 = p3[:2]

                self._write(mgc, b'QUAD')
                self._write(f32 + f32 + f32 + f32 + f32 + f32, x1, y1, x2, y2, x3, y3)

    def _flush(self):
        self._fh.flush()
        self._fh.close()

    def export_frame(self, vgroup: VGroup, frame_number):

        # Gather all drawable VMobjects
        flat_vmobjs: List[VMobject] = list(
            extract_mobject_family_members(
                vgroup,
                only_those_with_points=True,
            )
        )

        self._emit_frame(len(flat_vmobjs))

        for vmobj in flat_vmobjs:
            self._emit_vmobject(vmobj)

        pass
