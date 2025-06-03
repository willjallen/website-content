//
// Created by William Allen on 5/29/25.
//

#ifndef MANIM_FE_H
#define MANIM_FE_H

#include "common/core.h"
#include <stdint.h>
#include <stdio.h>
#include <cairo.h>

#pragma pack(push, 1)

/**
 * ===================================
 *      MANIM DATA FILE DEFS
 * ===================================
 */

/**
 * File structure looks like this:
 *
 * [CTXT]
 *  [FRAM]
 *    [VM0B]
 *      [RGBA] (stroke background)
 *      ...
 *      [RGBA] (stroke background)
 *
 *      [RGBA] (stroke)
 *      ...
 *      [RGBA] (stroke)
 *
 *       [RGBA] (fill)
 *      ...
 *      [RGBA] (fill)
 *
 *      [SUBP]
 *        [QUAD]
 *        ...
 *        [QUAD]
 *      [SUBP]
 *
 *      ...
 *      [SUBP]
 *
 *    [VMOB]
 *    ...
 *    [VMOB]
 *   [FRAM]
 *   ...
 *   [FRAM]
 */

typedef struct {
  char magic[4]; /** RGBA **/
  float vals[4];
} rgba_t;

typedef struct {
  char magic[4]; /** QUAD **/
  float x1, y1;
  float x2, y2;
  float x3, y3;
} quad_t;

typedef struct {
  char magic[4]; /** SUBP **/
  float x, y;
  uint32_t quad_count;
  quad_t *quads;
} subpath_t;

typedef struct {
  char magic[4]; /** VMOB **/

  uint32_t id;

  /** Style **/
  float stroke_bg_width;
  float stroke_width;

  uint32_t stroke_bg_rgbas_count;
  uint32_t stroke_rgbas_count;

  uint32_t fill_rgbas_count;

  float gradient_x0, gradient_y0;
  float gradient_x1, gradient_y1;

  /** Subpaths **/
  uint32_t subpath_count;

  rgba_t *stroke_bg_rgbas;
  rgba_t *stroke_rgbas;
  rgba_t *fill_rgbas;

  subpath_t *subpaths;

} vmo_t;

typedef struct {
  char magic[4]; /** FRAM **/
  uint32_t vmo_count;
  vmo_t *vmos;
} frame_t;

typedef struct {
  char magic[4]; /** CTXT **/
  uint32_t version;
  double pixel_width, pixel_height;
  double frame_width, frame_height;
} file_header_t;

#pragma pack(pop)

/**
 * ===================================
 *             FILE I/O
 * ===================================
 */

int read_header(FILE *fp, file_header_t *file_header);
int read_frame(FILE *fp, frame_t *frame);
void free_frame(const frame_t *frame);

/**
 * ===================================
 *             SVG RENDERING
 * ===================================
 */

typedef enum context_color_t { FILL, STROKE, STROKE_BG } context_color_t;

int init_cairo_ctx(cairo_t *ctx, const file_header_t *file_header);

int render_frame(cairo_t *ctx, const frame_t *frame);

int render_vmo(cairo_t *ctx, const vmo_t *vmo);

cairo_status_t cairo_buffer_writer(void *closure, const unsigned char *data,
                             unsigned int length);

void set_cairo_context_color(cairo_t *ctx, const vmo_t *vmo,
                             context_color_t context_color_type);

void apply_stroke(cairo_t *ctx, const vmo_t *vmo, bool background);

void apply_fill(cairo_t *ctx, const vmo_t *vmo);

int manim_fe_driver(const char *in_file_path,
                    svg_frame_buffers_t *out_svg_frame_buffer);

#endif // MANIM_FE_H
