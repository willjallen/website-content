#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <cairo.h>

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
  float rgba[4];
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

void free_frame(Frame *F) {
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
  while (read_frame(fp, &frame)) {
    // render_frame(&frame);
    // printf("%d", frame.vmo_count);
    free_frame(&frame);
  }

  fclose(fp);
        cairo_surface_t *surface =
            cairo_image_surface_create (CAIRO_FORMAT_ARGB32, 240, 80);
        cairo_t *cr =
            cairo_create (surface);

        cairo_select_font_face (cr, "serif", CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD);
        cairo_set_font_size (cr, 32.0);
        cairo_set_source_rgb (cr, 0.0, 0.0, 1.0);
        cairo_move_to (cr, 10.0, 50.0);
        cairo_show_text (cr, "Hello, world");

        cairo_destroy (cr);
        cairo_surface_write_to_png (surface, "E:\\APP\\website-content\\manim\\newtons-fractal\\hello.png");
        cairo_surface_destroy (surface);
        return 0;
}
