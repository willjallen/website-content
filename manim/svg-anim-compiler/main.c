#include <cairo-svg.h>
#include <cairo.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ctrs/map.h"
#include "ctrs/map_test.h"

#include <tgmath.h>

/**
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
 *
 *
 *
 *
 */

#pragma pack(push, 1)

typedef struct {
  char magic[4]; /** RGBA **/
  float vals[4];
} RGBA;

typedef struct {
  char magic[4]; /** QUAD **/
  float x1, y1;
  float x2, y2;
  float x3, y3;
} Quad;

typedef struct {
  char magic[4]; /** SUBP **/
  float x, y;
  uint32_t quad_count;
  Quad *quads;
} Subpath;

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

  RGBA *stroke_bg_rgbas;
  RGBA *stroke_rgbas;
  RGBA *fill_rgbas;

  Subpath *subpaths;

} VMO;

typedef struct {
  char magic[4]; /** FRAM **/
  uint32_t vmo_count;
  VMO *vmos;
} Frame;

typedef struct {
  char magic[4]; /** CTXT **/
  uint32_t version;
  uint32_t pixel_width, pixel_height;
  float frame_width, frame_height;
} FileHeader;

#pragma pack(pop)

#if _MSC_VER
#define likely(x) x
#define unlikely(x) x
#else
#define likely(x) __builtin_expect(!!(x), 1)
#define unlikely(x) __builtin_expect(!!(x), 0)
#endif

int read_header(FILE *fp, FileHeader *fileHeader);
int read_frame(FILE *fp, Frame *frame);
int render_frame(cairo_t *ctx, cairo_surface_t *surface, Frame *frame,
                 FileHeader *file_header);

cairo_status_t buffer_writer(void *closure, const unsigned char *data,
                             unsigned int length);

typedef struct CairoSVGBuffer {
  unsigned char *data;
  size_t size;
  size_t capacity;
} CairoSVGBuffer;

cairo_status_t buffer_writer(void *closure, const unsigned char *data,
                             unsigned int length) {
  CairoSVGBuffer *buffer = closure;

  size_t new_capacity = buffer->capacity;
  if (buffer->size + length > buffer->capacity) {
    new_capacity = buffer->capacity ? buffer->capacity * 2 : 4096;
    while (new_capacity < buffer->size + length)
      new_capacity *= 2;

    void *new_data = realloc(buffer->data, new_capacity);
    if (!new_data)
      return CAIRO_STATUS_NO_MEMORY;

    buffer->data = new_data;
    buffer->capacity = new_capacity;
  }

  memcpy(buffer->data + buffer->size, data, length);
  buffer->size += length;

  return CAIRO_STATUS_SUCCESS;
}

// def _set_cairo_context_color(ctx: cairo.Context, rgbas: np.ndarray, vmobject:
// VMobject):
//     """Set *ctx*'s current colour or gradient fill from *rgbas*."""
//     if len(rgbas) == 1:
//         ctx.set_source_rgba(*rgbas[0])
//         return
//
//     points = vmobject.get_gradient_start_and_end_points()
//     points = _transform_points_pre_display(points)
//     pat = cairo.LinearGradient(*itertools.chain(*(p[:2] for p in points)))
//     step = 1.0 / (len(rgbas) - 1)
//     offsets = np.arange(0, 1 + step, step)
//     for rgba, offset in zip(rgbas, offsets):
//         pat.add_color_stop_rgba(offset, *rgba)
//     ctx.set_source(pat)

typedef enum ContextColorType { FILL, STROKE, STROKE_BG } ContextColorType;

void set_cairo_context_color(cairo_t *ctx, VMO *vmo,
                             ContextColorType context_color_type) {

  uint32_t rgba_count = 0;
  RGBA *rgbas = NULL;
  if (context_color_type == FILL) {
    rgba_count = vmo->fill_rgbas_count;
    rgbas = vmo->fill_rgbas;
  } else if (context_color_type == STROKE) {
    rgba_count = vmo->stroke_rgbas_count;
    rgbas = vmo->stroke_rgbas;
  } else if (context_color_type == STROKE_BG) {
    rgba_count = vmo->stroke_bg_rgbas_count;
    rgbas = vmo->stroke_bg_rgbas;
  }

  if (rgba_count == 1) {
    RGBA *rgba = &rgbas[0];
    cairo_set_source_rgba(ctx, rgba->vals[0], rgba->vals[1], rgba->vals[2],
                          rgba->vals[3]);
    return;
  }

  cairo_pattern_t *pat = cairo_pattern_create_linear(
      vmo->gradient_x0, vmo->gradient_y0, vmo->gradient_x1, vmo->gradient_y1);
  double step = 1.0 / (vmo->fill_rgbas_count - 1);

  double val = 0;
  for (int i = 0; i < vmo->fill_rgbas_count; i++) {
    RGBA *rgba = &rgbas[i];
    cairo_pattern_add_color_stop_rgba(pat, step, rgba->vals[0], rgba->vals[1],
                                      rgba->vals[2], rgba->vals[3]);
    val += step;
  }
  cairo_set_source(ctx, pat);
}

void apply_stroke(cairo_t *ctx, VMO *vmo, bool background) {
  double width = background ? vmo->stroke_bg_width : vmo->stroke_width;
  if (width == 0)
    return;

  set_cairo_context_color(ctx, vmo, background ? STROKE_BG : STROKE);
  cairo_set_line_width(ctx, width * 0.01); // 0.01?
  cairo_stroke_preserve(ctx);
}

void apply_fill(cairo_t *ctx, VMO *vmo) {
  set_cairo_context_color(ctx, vmo, FILL);
  cairo_fill_preserve(ctx);
}

//
// def _apply_stroke(ctx: cairo.Context, vm: VMobject, *, background: bool =
// False):
//     width = vm.get_stroke_width(background)
//     if width == 0:
//         return
//
//     _set_cairo_context_color(ctx, vm.get_stroke_rgbas(background), vm)
//     ctx.set_line_width(width * CAIRO_LINE_WIDTH_MULTIPLE)
//     ctx.stroke_preserve()
//
//
// def _apply_fill(ctx: cairo.Context, vm: VMobject):
//     _set_cairo_context_color(ctx, vm.get_fill_rgbas(), vm)
//     ctx.fill_preserve()

int render_frame(cairo_t *ctx, cairo_surface_t *surface, Frame *frame,
                 FileHeader *file_header) {
  cairo_scale(ctx, file_header->pixel_width, file_header->pixel_height);
  cairo_matrix_t matrix;
  cairo_matrix_init(
      &matrix, file_header->pixel_width / file_header->frame_width, 0, 0,
      -(file_header->pixel_width / file_header->frame_height),
      (file_header->pixel_width / 2) -
          0 * (file_header->pixel_width / file_header->frame_width),
      (file_header->pixel_height / 2) +
          0 * (file_header->pixel_height / file_header->frame_height));

  cairo_set_matrix(ctx, &matrix);

  for (int i = 0; i < frame->vmo_count; i++) {
    VMO *vmo = &frame->vmos[i];
    printf("%d\n", vmo->id);

    cairo_new_path(ctx);
    for (int j = 0; j < vmo->subpath_count; j++) {
      Subpath *subpath = &vmo->subpaths[j];
      cairo_new_sub_path(ctx);
      cairo_move_to(ctx, subpath->x, subpath->y);
      for (int k = 0; k < subpath->quad_count; k++) {
        Quad *quad = &subpath->quads[k];
        cairo_curve_to(ctx, quad->x1, quad->y1, quad->x2, quad->y2, quad->x3,
                       quad->y3);
      }

      Subpath *first = &subpath[0];
      Subpath *last = &subpath[vmo->subpath_count - 1];

      // TODO: Shitty.
      // if (fabs(first->x - last->x) < 1e-6 && fabs(first->y - last->y) < 1e-6)
      // {
      cairo_close_path(ctx);
      // }
    }

    apply_stroke(ctx, vmo, true);
    apply_fill(ctx, vmo);
    apply_stroke(ctx, vmo, false);
  }
}

/**
 * ============================================================================
 *                                FILE IO
 * ============================================================================
 */
int read_header(FILE *fp, FileHeader *fileHeader) {
  fread(fileHeader, sizeof(*fileHeader), 1, fp);

  if (memcmp(fileHeader->magic, "CTXT", 4) != 0) {
    printf("File header magic malformed.");
    return 0;
  }

  return 1;
}

int read_frame(FILE *fp, Frame *frame) {
  fread(&frame->magic, sizeof(frame->magic), 1, fp);

  if (unlikely(memcmp(frame->magic, "FRAM", 4) != 0)) {
    printf("Frame header magic malformed.");
    return 0;
  }

  if (fread(&frame->vmo_count, sizeof(frame->vmo_count), 1, fp) != 1)
    return 0;

  // Allocate vmos
  // TODO: How slow is this?
  frame->vmos = calloc(frame->vmo_count, sizeof(VMO));

  for (uint32_t i = 0; i < frame->vmo_count; i++) {
    VMO *vmo = &frame->vmos[i];

    // Read up to first pointer
    fread(vmo, offsetof(VMO, stroke_bg_rgbas), 1, fp);

    // Stroke background RGBAs
    vmo->stroke_bg_rgbas = calloc(vmo->stroke_bg_rgbas_count, sizeof(RGBA));
    fread(vmo->stroke_bg_rgbas, sizeof(RGBA), vmo->stroke_bg_rgbas_count, fp);

    // Stroke RGBAs
    vmo->stroke_rgbas = calloc(vmo->stroke_rgbas_count, sizeof(RGBA));
    fread(vmo->stroke_rgbas, sizeof(RGBA), vmo->stroke_rgbas_count, fp);

    // Fill RGBAs
    vmo->fill_rgbas = calloc(vmo->fill_rgbas_count, sizeof(RGBA));
    fread(vmo->fill_rgbas, sizeof(RGBA), vmo->fill_rgbas_count, fp);

    // Subpaths
    vmo->subpaths = calloc(vmo->subpath_count, sizeof(Subpath));
    for (uint32_t j = 0; j < vmo->subpath_count; j++) {
      Subpath *subpath = &vmo->subpaths[j];

      // Read up to first pointer
      fread(subpath, offsetof(Subpath, quads), 1, fp);

      // Quads
      subpath->quads = calloc(subpath->quad_count, sizeof(Quad));
      fread(subpath->quads, sizeof(Quad), subpath->quad_count, fp);
    }
  }

  return 1;
}

void free_frame(const Frame *F) {
  for (uint32_t i = 0; i < F->vmo_count; ++i) {
    const VMO *vmo = &F->vmos[i];
    free(vmo->stroke_bg_rgbas);
    free(vmo->stroke_rgbas);
    free(vmo->fill_rgbas);
    for (uint32_t s = 0; s < vmo->subpath_count; ++s)
      free(vmo->subpaths[s].quads);
    free(vmo->subpaths);
  }
  free(F->vmos);
}

// int render_frame(Frame *frame) { return frame; }

int main(int argc, char **argv) {
  if (argc != 2) {
    fprintf(stderr, "Usage: %s <inDataFile>\n", argv[0]);
    return 1;
  }

  const char *inDataFile = argv[1];
  printf("Reading from: %s\n", inDataFile);

  FILE *fp = fopen(inDataFile, "rb");
  if (!fp) {
    perror("fopen failed");
    return 1;
  }

  FileHeader file_header;
  read_header(fp, &file_header);

  Frame frame;
  int frame_index = 0;
  while (read_frame(fp, &frame)) {

    CairoSVGBuffer cairo_svg_buffer;
    // cairo_surface_t *surface =
    //     cairo_svg_surface_create_for_stream(buffer_writer, &cairo_svg_buffer,
    //     file_header.pixel_width, file_header.pixel_height);
    cairo_surface_t *surface =
        cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 800, 600);
    cairo_t *ctx = cairo_create(surface);

    render_frame(ctx, surface, &frame, &file_header);

    // cairo_select_font_face (ctx, "serif", CAIRO_FONT_SLANT_NORMAL,
    // CAIRO_FONT_WEIGHT_BOLD); cairo_set_font_size (ctx, 32.0);
    // cairo_set_source_rgb (ctx, 0.0, 0.0, 1.0);
    // cairo_move_to (ctx, 10.0, 50.0);
    // cairo_show_text (ctx, "Hello, world");
    //
    cairo_destroy(ctx);

    // SLOW!!
    char filename[256];
    snprintf(filename, sizeof(filename),
             "/Users/will/Documents/APP/website-content/manim/newtons-fractal/"
             "test/%d.png",
             frame_index);
    cairo_surface_write_to_png(surface, filename);

    cairo_surface_destroy(surface);
    // render_frame(&frame);
    // printf("%d", frame.vmo_count);
    free_frame(&frame);
    ++frame_index;
  }

  fclose(fp);

  // Map *map = map_create(4, 8);
  // map_create(sizeof(uint8_t), alignof(uint8_t));
  // map_tests_run_all();
  return 0;
}

