#include <cairo-svg.h>
#include <cairo.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

#include "ctrs/map.h"
#include "ctrs/map_test.h"

#include "manim/manim_fe.h"
#include "common/core.h"

/**
 * ===================================
 *             FILE I/O
 * ===================================
 */
int read_header(FILE *fp, file_header_t *file_header) {
  fread(file_header, sizeof(*file_header), 1, fp);

  if (memcmp(file_header->magic, "CTXT", 4) != 0) {
    printf("File header magic malformed.");
    return 0;
  }

  return 1;
}

int read_frame(FILE *fp, frame_t *frame) {
  fread(&frame->magic, sizeof(frame->magic), 1, fp);

  if (unlikely(memcmp(frame->magic, "FRAM", 4) != 0)) {
    printf("Frame header magic malformed.");
    return 0;
  }

  if (fread(&frame->vmo_count, sizeof(frame->vmo_count), 1, fp) != 1)
    return 0;

  // Allocate vmos
  // TODO: How slow is this?
  frame->vmos = calloc(frame->vmo_count, sizeof(vmo_t));

  for (uint32_t i = 0; i < frame->vmo_count; i++) {
    vmo_t *vmo = &frame->vmos[i];

    // Read up to first pointer
    fread(vmo, offsetof(vmo_t, stroke_bg_rgbas), 1, fp);

    // Stroke background RGBAs
    vmo->stroke_bg_rgbas = calloc(vmo->stroke_bg_rgbas_count, sizeof(rgba_t));
    fread(vmo->stroke_bg_rgbas, sizeof(rgba_t), vmo->stroke_bg_rgbas_count, fp);

    // Stroke RGBAs
    vmo->stroke_rgbas = calloc(vmo->stroke_rgbas_count, sizeof(rgba_t));
    fread(vmo->stroke_rgbas, sizeof(rgba_t), vmo->stroke_rgbas_count, fp);

    // Fill RGBAs
    vmo->fill_rgbas = calloc(vmo->fill_rgbas_count, sizeof(rgba_t));
    fread(vmo->fill_rgbas, sizeof(rgba_t), vmo->fill_rgbas_count, fp);

    // Subpaths
    vmo->subpaths = calloc(vmo->subpath_count, sizeof(subpath_t));
    for (uint32_t j = 0; j < vmo->subpath_count; j++) {
      subpath_t *subpath = &vmo->subpaths[j];

      // Read up to first pointer
      fread(subpath, offsetof(subpath_t, quads), 1, fp);

      // Quads
      subpath->quads = calloc(subpath->quad_count, sizeof(quad_t));
      fread(subpath->quads, sizeof(quad_t), subpath->quad_count, fp);
    }
  }

  return 1;
}

void free_frame(const frame_t *frame) {
  for (uint32_t i = 0; i < frame->vmo_count; ++i) {
    const vmo_t *vmo = &frame->vmos[i];
    free(vmo->stroke_bg_rgbas);
    free(vmo->stroke_rgbas);
    free(vmo->fill_rgbas);
    for (uint32_t s = 0; s < vmo->subpath_count; ++s)
      free(vmo->subpaths[s].quads);
    free(vmo->subpaths);
  }
  free(frame->vmos);
}

/**
 * ===================================
 *             SVG RENDERING
 * ===================================
 */

int init_cairo_ctx(cairo_t *ctx, const file_header_t *file_header) {
  double fw = file_header->frame_width;
  double fh = file_header->frame_height;

  double pw = file_header->pixel_width;
  double ph = file_header->pixel_height;

  cairo_scale(ctx, pw, ph);
  cairo_matrix_t matrix;
  cairo_matrix_init(&matrix, pw / fw, 0, 0, -(ph / fh), (pw / 2), (ph / 2));

  cairo_set_matrix(ctx, &matrix);
  return 1;
}

int render_frame(cairo_t *ctx, const frame_t *frame) {
  
  for (int i = 0; i < frame->vmo_count; i++) {
    vmo_t *vmo = &frame->vmos[i];
    printf("%d\n", vmo->id);

    cairo_new_path(ctx);
    for (int j = 0; j < vmo->subpath_count; j++) {
      subpath_t *subpath = &vmo->subpaths[j];
      cairo_new_sub_path(ctx);
      cairo_move_to(ctx, subpath->x, subpath->y);
      for (int k = 0; k < subpath->quad_count; k++) {
        quad_t *quad = &subpath->quads[k];
        cairo_curve_to(ctx, quad->x1, quad->y1, quad->x2, quad->y2, quad->x3,
                       quad->y3);
      }

      subpath_t *first = &subpath[0];
      subpath_t *last = &subpath[vmo->subpath_count - 1];

      // TODO: Shitty.
      if (fabs(first->x - last->x) < 1e-6 && fabs(first->y - last->y) < 1e-6) {
        cairo_close_path(ctx);
      }
    }

    apply_stroke(ctx, vmo, true);
    apply_fill(ctx, vmo);
    apply_stroke(ctx, vmo, false);
  }

  return 1;
}

int render_vmo(cairo_t *ctx, const vmo_t *vmo) {
  
  cairo_new_path(ctx);
  for (int j = 0; j < vmo->subpath_count; j++) {
    subpath_t *subpath = &vmo->subpaths[j];
    cairo_new_sub_path(ctx);
    cairo_move_to(ctx, subpath->x, subpath->y);
    for (int k = 0; k < subpath->quad_count; k++) {
      quad_t *quad = &subpath->quads[k];
      cairo_curve_to(ctx, quad->x1, quad->y1, quad->x2, quad->y2, quad->x3,
                     quad->y3);
    }

    subpath_t *first = &subpath[0];
    subpath_t *last = &subpath[vmo->subpath_count - 1];

    // TODO: Shitty.
    if (fabs(first->x - last->x) < 1e-6 && fabs(first->y - last->y) < 1e-6) {
      cairo_close_path(ctx);
    }
  }

  apply_stroke(ctx, vmo, true);
  apply_fill(ctx, vmo);
  apply_stroke(ctx, vmo, false);

  return 1;
}

cairo_status_t buffer_writer(void *closure, const unsigned char *data,
                             unsigned int length) {
  buffer_t *buffer = closure;

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

void set_cairo_context_color(cairo_t *ctx, vmo_t *vmo,
                             const context_color_t context_color_type) {

  uint32_t rgba_count = 0;
  rgba_t *rgbas = NULL;
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
    rgba_t *rgba = &rgbas[0];
    cairo_set_source_rgba(ctx, rgba->vals[0], rgba->vals[1], rgba->vals[2],
                          rgba->vals[3]);
    return;
  }

  cairo_pattern_t *pat = cairo_pattern_create_linear(
      vmo->gradient_x0, vmo->gradient_y0, vmo->gradient_x1, vmo->gradient_y1);
  double step = 1.0 / (vmo->fill_rgbas_count - 1);

  double val = 0;
  for (int i = 0; i < vmo->fill_rgbas_count; i++) {
    rgba_t *rgba = &rgbas[i];
    cairo_pattern_add_color_stop_rgba(pat, step, rgba->vals[0], rgba->vals[1],
                                      rgba->vals[2], rgba->vals[3]);
    val += step;
  }
  cairo_set_source(ctx, pat);
}

void apply_stroke(cairo_t *ctx, vmo_t *vmo, bool background) {
  double width = background ? vmo->stroke_bg_width : vmo->stroke_width;
  if (width == 0)
    return;

  set_cairo_context_color(ctx, vmo, background ? STROKE_BG : STROKE);
  cairo_set_line_width(ctx, width * 0.01); // 0.01?
  cairo_stroke_preserve(ctx);
}

void apply_fill(cairo_t *ctx, vmo_t *vmo) {
  set_cairo_context_color(ctx, vmo, FILL);
  cairo_fill_preserve(ctx);
}

int manim_fe_driver(const char *in_file_path,
                    svg_frame_buffers_t *out_svg_frame_buffers) {

  printf("Reading from: %s\n", in_file_path);

  FILE *fp = fopen(in_file_path, "rb");
  if (!fp) {
    perror("fopen failed");
    return 1;
  }

  file_header_t file_header;
  read_header(fp, &file_header);

  frame_t frame;
  int frame_index = 0;
  out_svg_frame_buffers->svg_frames = malloc(1000000);
  while (read_frame(fp, &frame)) {

    //     
    /**
     * read frame ->
     * collect each vmo svg path ->
     * strip header/tail ->
     * append id to svg path ->
     * concat
     */

    buffer_t *svg_frame_buffer =
        &out_svg_frame_buffers->svg_frames[frame_index];

    // Append svg header
    char svg_header[256];
    snprintf(svg_header, sizeof(svg_header),
             "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
             "<svg xmlns=\"http://www.w3.org/2000/svg\" xmlns:xlink=\"http://www.w3.org/1999/xlink\" "
             "width=\"%f\" height=\"%f\" viewBox=\"0 0 %f %f\" style=\"background: black\">",
             file_header.pixel_width, file_header.pixel_height,
             file_header.pixel_width, file_header.pixel_height);
    buffer_writer(svg_frame_buffer, (unsigned char*)svg_header, strlen(svg_header));

    
    for (int i = 0; i < frame.vmo_count; i++) {
      buffer_t vmo_svg_buffer;
      init_buffer(&vmo_svg_buffer);
      cairo_surface_t *surface = cairo_svg_surface_create_for_stream(
          buffer_writer, &vmo_svg_buffer, file_header.pixel_width,
          file_header.pixel_height);
      cairo_t *ctx = cairo_create(surface);

      init_cairo_ctx(ctx, &file_header);
      
      vmo_t *vmo = &frame.vmos[i];
      // printf("%d\n", vmo->id);
      render_vmo(ctx, vmo);
      
      cairo_destroy(ctx);

      // cairo flushes svg text to stream here
      cairo_surface_destroy(surface);

      // Null-terminate the SVG data for safe string operations
      buffer_writer(&vmo_svg_buffer, "\0", 1);
      
      // extract <path>
      const char *svg_str = vmo_svg_buffer.data;
      const char *path_str_begin = strstr(svg_str, "<path ");

      if (path_str_begin == NULL) {
        // Cairo did not emit a <path> for this vmo, bail.
        continue;
      }
      
      const char *path_str_end = strstr(path_str_begin, "\n");

      size_t count = path_str_end - path_str_begin;
      
      const char path_str[count];
      strncpy(path_str, path_str_begin, count);
      
      buffer_writer(svg_frame_buffer, path_str, count);
      buffer_writer(svg_frame_buffer, "\n", 1);
    }

    // Append closing svg tag
    const unsigned char *svg_closer = "</svg>";
    buffer_writer(svg_frame_buffer, svg_closer, strlen((char*)svg_closer));
    
    printf("%s", svg_frame_buffer->data);
    // Dump SVG data to a file named <frame_index>.svg
    {
      char filename[512];
      snprintf(filename, sizeof(filename),
               "/Users/will/Documents/APP/website-content/manim/newtons-fractal/test/%d.svg",
               frame_index);
      FILE *fout = fopen(filename, "wb");
      if (fout) {
        fwrite(svg_frame_buffer->data, 1, svg_frame_buffer->size, fout);
        fclose(fout);
      } else {
        perror("fopen SVG output failed");
      }
    }
    
    free_frame(&frame);
    ++frame_index;
  }
  
  out_svg_frame_buffers->num_frames = frame_index;

  
  fclose(fp);
  return 0;
}
