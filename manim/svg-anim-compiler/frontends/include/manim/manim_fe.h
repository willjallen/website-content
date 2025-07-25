//
// Created by William Allen on 5/29/25.
//

#ifndef MANIM_FE_H
#define MANIM_FE_H

#include <stdint.h>
#include <stdio.h>
#include <cairo.h>
#include <stdbool.h>


#include "common/core.h"
#include "common/arena.h"

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
} manim_rgba_t;

typedef struct {
  char magic[4]; /** QUAD **/
  float x1, y1;
  float x2, y2;
  float x3, y3;
} manim_quad_t;

typedef struct {
  char magic[4]; /** SUBP **/
  float x, y;
  uint32_t quad_count;
  manim_quad_t *quads;
} manim_subpath_t;

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

  manim_rgba_t *stroke_bg_rgbas;
  manim_rgba_t *stroke_rgbas;
  manim_rgba_t *fill_rgbas;

  manim_subpath_t *subpaths;

} manim_vmo_t;

typedef struct {
  char magic[4]; /** FRAM **/
  uint32_t vmo_count;
  manim_vmo_t *vmos;
} manim_frame_t;

typedef struct {
  char magic[4]; /** CTXT **/
  uint32_t version;
  double pixel_width, pixel_height;
  double frame_width, frame_height;
} manim_file_header_t;

#pragma pack(pop)

/**
 * ===================================
 *             FILE I/O
 * ===================================
 */

int read_header(FILE *fp, manim_file_header_t *file_header);
int read_frame(arena_t *frame_arena, FILE *fp, manim_frame_t *frame);
void free_frame(const manim_frame_t *frame);

/**
 * ===================================
 *             SVG RENDERING
 * ===================================
 */

typedef enum context_color_t { C_FILL, C_STROKE, C_STROKE_BG } context_color_t;

int init_cairo_ctx(cairo_t *ctx, const manim_file_header_t *file_header);

int render_vmo(cairo_t *ctx, const manim_vmo_t *vmo);

cairo_status_t cairo_buffer_writer(void *closure, const unsigned char *data,
                             unsigned int length);

void set_cairo_context_color(cairo_t *ctx, const manim_vmo_t *vmo,
                             context_color_t context_color_type);

void apply_stroke(cairo_t *ctx, const manim_vmo_t *vmo, bool background);

void apply_fill(cairo_t *ctx, const manim_vmo_t *vmo);

/**
 *  @brief Ingests a data binary from the manim-fast-svg plugin and emits a
 *  sequence of svg frames with data-tag ids appended to each <path>.
 *
 * @param svg_frames_blob_arena Arena for svg blobs.
 * @param svg_frames_record_arena Arena for svg records.
 * @param file_path Input manim data binary to process.
 * @param out_svg_frames Output tagged svg frames.
 * @return
 */
int manim_fe_driver(arena_t *svg_frames_blob_arena, arena_t *svg_frames_record_arena, const char *file_path,
                    svg_frames_t **out_svg_frames);

#endif // MANIM_FE_H
