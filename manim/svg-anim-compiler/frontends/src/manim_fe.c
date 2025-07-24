#include <cairo-svg.h>
#include <cairo.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "ctrs/map.h"

#include "common/arena.h"
#include "common/core.h"
#include "manim/manim_fe.h"

/**
 * ===================================
 *             FILE I/O
 * ===================================
 */
int read_header(FILE *fp, manim_file_header_t *file_header) {
  fread(file_header, sizeof(*file_header), 1, fp);

  if (memcmp(file_header->magic, "CTXT", 4) != 0) {
    printf("File header magic malformed.");
    return 0;
  }

  return 1;
}

int read_frame(arena_t *frame_arena, FILE *fp, manim_frame_t *frame) {
  fread(&frame->magic, sizeof(frame->magic), 1, fp);

  if (unlikely(memcmp(frame->magic, "FRAM", 4) != 0)) {
    printf("Frame header magic malformed.");
    return 0;
  }

  if (fread(&frame->vmo_count, sizeof(frame->vmo_count), 1, fp) != 1)
    return 0;

  frame->vmos = arena_push_array(frame_arena, manim_vmo_t, frame->vmo_count);

  for (uint32_t i = 0; i < frame->vmo_count; i++) {
    manim_vmo_t *vmo = &frame->vmos[i];

    // Read up to first pointer
    fread(vmo, offsetof(manim_vmo_t, stroke_bg_rgbas), 1, fp);

    // Stroke background RGBAs
    vmo->stroke_bg_rgbas =
        arena_push_array(frame_arena, manim_rgba_t, vmo->stroke_bg_rgbas_count);
    fread(vmo->stroke_bg_rgbas, sizeof(manim_rgba_t),
          vmo->stroke_bg_rgbas_count, fp);

    // Stroke RGBAs
    vmo->stroke_rgbas =
        arena_push_array(frame_arena, manim_rgba_t, vmo->stroke_rgbas_count);
    fread(vmo->stroke_rgbas, sizeof(manim_rgba_t), vmo->stroke_rgbas_count, fp);

    // Fill RGBAs
    vmo->fill_rgbas =
        arena_push_array(frame_arena, manim_rgba_t, vmo->fill_rgbas_count);
    fread(vmo->fill_rgbas, sizeof(manim_rgba_t), vmo->fill_rgbas_count, fp);

    // Subpaths
    vmo->subpaths =
        arena_push_array(frame_arena, manim_subpath_t, vmo->subpath_count);
    for (uint32_t j = 0; j < vmo->subpath_count; j++) {
      manim_subpath_t *subpath = &vmo->subpaths[j];

      // Read up to first pointer
      fread(subpath, offsetof(manim_subpath_t, quads), 1, fp);

      // Quads
      subpath->quads =
          arena_push_array(frame_arena, manim_quad_t, subpath->quad_count);
      fread(subpath->quads, sizeof(manim_quad_t), subpath->quad_count, fp);
    }
  }

  return 1;
}

/**
 * ===================================
 *             SVG RENDERING
 * ===================================
 */

int init_cairo_ctx(cairo_t *ctx, const manim_file_header_t *file_header) {
  const double fw = file_header->frame_width;
  const double fh = file_header->frame_height;

  const double pw = file_header->pixel_width;
  const double ph = file_header->pixel_height;

  cairo_scale(ctx, pw, ph);
  cairo_matrix_t matrix;
  cairo_matrix_init(&matrix, pw / fw, 0, 0, -(ph / fh), (pw / 2), (ph / 2));

  cairo_set_matrix(ctx, &matrix);
  return 1;
}

int render_vmo(cairo_t *ctx, const manim_vmo_t *vmo) {

  cairo_new_path(ctx);
  for (uint32_t j = 0; j < vmo->subpath_count; j++) {
    manim_subpath_t *subpath = &vmo->subpaths[j];
    cairo_new_sub_path(ctx);
    cairo_move_to(ctx, subpath->x, subpath->y);
    for (uint32_t k = 0; k < subpath->quad_count; k++) {
      const manim_quad_t *quad = &subpath->quads[k];
      cairo_curve_to(ctx, quad->x1, quad->y1, quad->x2, quad->y2, quad->x3,
                     quad->y3);
    }

    manim_subpath_t *first = &subpath[0];
    manim_subpath_t *last = &subpath[vmo->subpath_count - 1];

    // TODO: Shitty.
    if (fabsf(first->x - last->x) < 1e-6 && fabsf(first->y - last->y) < 1e-6) {
      cairo_close_path(ctx);
    }
  }

  apply_stroke(ctx, vmo, true);
  apply_fill(ctx, vmo);
  apply_stroke(ctx, vmo, false);

  return 1;
}

cairo_status_t cairo_buffer_writer(void *closure, const unsigned char *data,
                                   const unsigned int length) {
  arena_t *arena = closure;
  void *dest = arena_push(arena, length);
  if (!dest)
    return CAIRO_STATUS_NO_MEMORY;
  memcpy(dest, data, length);
  return CAIRO_STATUS_SUCCESS;
}

void set_cairo_context_color(cairo_t *ctx, const manim_vmo_t *vmo,
                             const context_color_t context_color_type) {

  uint32_t rgba_count = 0;
  manim_rgba_t *rgbas = NULL;
  if (context_color_type == C_FILL) {
    rgba_count = vmo->fill_rgbas_count;
    rgbas = vmo->fill_rgbas;
  } else if (context_color_type == C_STROKE) {
    rgba_count = vmo->stroke_rgbas_count;
    rgbas = vmo->stroke_rgbas;
  } else if (context_color_type == C_STROKE_BG) {
    rgba_count = vmo->stroke_bg_rgbas_count;
    rgbas = vmo->stroke_bg_rgbas;
  }

  if (rgba_count == 1) {
    manim_rgba_t *rgba = &rgbas[0];
    cairo_set_source_rgba(ctx, rgba->vals[0], rgba->vals[1], rgba->vals[2],
                          rgba->vals[3]);
    return;
  }

  cairo_pattern_t *pat = cairo_pattern_create_linear(
      vmo->gradient_x0, vmo->gradient_y0, vmo->gradient_x1, vmo->gradient_y1);
  double step = 1.0 / (rgba_count - 1);

  double val = 0;
  for (uint32_t i = 0; i < rgba_count; i++) {
    manim_rgba_t *rgba = &rgbas[i];
    cairo_pattern_add_color_stop_rgba(pat, val, rgba->vals[0], rgba->vals[1],
                                      rgba->vals[2], rgba->vals[3]);
    val += step;
  }
  cairo_set_source(ctx, pat);
}

void apply_stroke(cairo_t *ctx, const manim_vmo_t *vmo, bool background) {
  double width = background ? vmo->stroke_bg_width : vmo->stroke_width;
  if (width == 0)
    return;

  set_cairo_context_color(ctx, vmo, background ? C_STROKE_BG : C_STROKE);
  cairo_set_line_width(ctx, width * 0.01); // 0.01?
  cairo_stroke_preserve(ctx);
}

void apply_fill(cairo_t *ctx, const manim_vmo_t *vmo) {
  set_cairo_context_color(ctx, vmo, C_FILL);
  cairo_fill_preserve(ctx);
}

int manim_fe_driver(arena_t *svg_frames_blob_arena,
                    arena_t *svg_frames_record_arena,
                    const char *file_path,
                    svg_frames_t **out_svg_frames) {
  printf("Starting Manim frontend driver..\n");

  timespec_t perf_total_start_time = ts_now();
  double perf_surface_destroy_cum_time = 0;

  printf("Reading from: %s\n", file_path);

  /** File handling **/
  FILE *fp = fopen(file_path, "rb");
  if (!fp) {
    perror("fopen failed");
    return 1;
  }

  /** Scratch Arenas **/
  arena_t *scratch_manim_frame_arena = arena_alloc();
  arena_t *scratch_string_arena = arena_alloc();
  arena_t *scratch_cairo_svg_arena = arena_alloc();

  /** Set up out_svg_frames header at the beginning of the blob **/
  *out_svg_frames = arena_push_struct(svg_frames_blob_arena, svg_frames_t);
  // Point frames to the svg slices/records in the meta arena
  (*out_svg_frames)->frames = (void *)svg_frames_record_arena->base;
  // Point the blob to where we are now in the blob arena, all svgs will follow
  (*out_svg_frames)->blob = (void *)svg_frames_blob_arena->base;

  /** Read manim file header **/
  manim_file_header_t file_header;
  read_header(fp, &file_header);

  /** Build svg frames **/
  int frame_index = 0;
  manim_frame_t manim_frame;
  while (read_frame(scratch_manim_frame_arena, fp, &manim_frame)) {

    /**
     * Build the SVG for the current animation frame
     *
     * 1. Read the next manim_frame_t from the input file.
     * 2. For every VMO in the frame:
     *      - Render the VMO to an in-memory Cairo SVG surface.
     *      - Extract the single <path .../> element generated by Cairo,
     *        discarding the surrounding <svg> prologue/epilogue.
     *      - Inject a data-tag="<vmo-id>" attribute given the vmo id.
     *      - Append the tagged path to the frame’s accumulating SVG buffer.
     * 3. After all VMOs are handled, append the closing </svg> tag.
     *
     * The result is one self-contained SVG document per frame.
     */

    /** Set up svg slice record **/
    svg_record_t *svg_record =
        arena_push_struct(svg_frames_record_arena, svg_record_t);
    // Update svg_length as we go
    svg_record->length = 0;
    size_t *svg_length = &svg_record->length;
    svg_record->offset = svg_frames_blob_arena->pos;

    /** Append svg header to svg blob **/
    char svg_header[256];
    snprintf(svg_header, sizeof(svg_header),
             "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
             "<svg xmlns=\"http://www.w3.org/2000/svg\" "
             "xmlns:xlink=\"http://www.w3.org/1999/xlink\" "
             "width=\"%f\" height=\"%f\" viewBox=\"0 0 %f %f\" "
             "style=\"background: black\">",
             file_header.pixel_width, file_header.pixel_height,
             file_header.pixel_width, file_header.pixel_height);

    size_t copy_bytes = strlen(svg_header);
    strncpy(arena_push(svg_frames_blob_arena, copy_bytes), svg_header,
            copy_bytes);
    *svg_length += copy_bytes;

    /** Append each svg path (1 per vmo) to svg blob **/
    for (uint32_t i = 0; i < manim_frame.vmo_count; i++) {

      /** Setup cairo surface and context **/
      cairo_surface_t *surface = cairo_svg_surface_create_for_stream(
          cairo_buffer_writer, scratch_cairo_svg_arena, file_header.pixel_width,
          file_header.pixel_height);
      cairo_t *ctx = cairo_create(surface);
      init_cairo_ctx(ctx, &file_header);

      /** Render the vmo to a <path> object **/
      const manim_vmo_t *vmo = &manim_frame.vmos[i];
      render_vmo(ctx, vmo);

      cairo_destroy(ctx);

      const timespec_t perf_surface_destroy_start_time = ts_now();
      // cairo flushes svg text to stream here
      cairo_surface_destroy(surface);
      const timespec_t perf_surface_destroy_end_time = ts_now();

      // Just in case, ensure cairo svg data is null terminated
      strncpy(arena_push(scratch_cairo_svg_arena, 1), "\0", 1);

      double perf_surface_destroy_total_time = ts_elapsed_sec(
          perf_surface_destroy_start_time, perf_surface_destroy_end_time);
      perf_surface_destroy_cum_time += perf_surface_destroy_total_time;

      /**
       * Now scratch_cairo_svg_arena contains a full svg, with the header and
       * closing tags included. We need to extract only the <path> object
       * from this, append the data-tag=<id> attribute to it, then append the
       * new tagged <path> object to our working svg frame.
       *
       * Note that sometimes cairo does not emit a <path> for the given vmo we
       * are processing. Cairo either thinks it's hidden, culled or unrenderable
       * for whatever reason. In this case, we bail and move on to the next vmo.
       */

      /** Extract <path> object **/
      const char *svg_str = (const char *)scratch_cairo_svg_arena->base;
      const char *path_str_begin = strstr(svg_str, "<path ");

      if (path_str_begin == NULL) {
        // Cairo did not emit a <path> for this vmo, bail.
        arena_clear(scratch_cairo_svg_arena);
        continue;
      }

      const char *path_str_end = strstr(path_str_begin, "/>");

      size_t count = (size_t)(path_str_end - path_str_begin);

      char *path_str = arena_push(scratch_string_arena, count + 1);
      memcpy(path_str, path_str_begin, count);
      path_str[count] = '\0';

      /** Append data-tag=<id> as an attribute at the end of the path **/
      copy_bytes = strlen(path_str) + snprintf(NULL, 0, "%u", vmo->id) + 32;
      char *tagged_path = arena_push(scratch_string_arena, copy_bytes);
      snprintf(tagged_path, copy_bytes, "%s data-tag=\"%u\"/>\n", path_str,
               vmo->id);

      /** Copy final tagged <path> path into blob arena **/
      copy_bytes = strlen(tagged_path);
      strncpy(arena_push(svg_frames_blob_arena, copy_bytes), tagged_path, copy_bytes);
      *svg_length += copy_bytes;

      arena_clear(scratch_cairo_svg_arena);
    }

    /** Append closing svg tag **/
    const char svg_close_tag[] = "</svg>";
    copy_bytes = strlen(svg_close_tag);
    strncpy(arena_push(svg_frames_blob_arena, copy_bytes), svg_close_tag, copy_bytes);
    *svg_length += copy_bytes;

    // printf("%s", svg_frame_buffer->data);
    // Dump SVG data to a file named <frame_index>.svg
    // {
    //   char filename[512];
    //   snprintf(filename, sizeof(filename),
    //            "/Users/will/Documents/APP/website-content/manim/"
    //            "newtons-fractal/test/%d.svg",
    //            frame_index);
    //   FILE *fout = fopen(filename, "wb");
    //   if (fout) {
    //     const void *src = svg_get_data(*out_svg_frames, frame_index);
    //     fwrite(src, 1, svg_record->length,
    //            fout);
    //     fclose(fout);
    //   } else {
    //     perror("fopen SVG output failed");
    //   }
    // }

    ++frame_index;
    arena_clear(scratch_cairo_svg_arena);
    arena_clear(scratch_string_arena);
    arena_clear(scratch_manim_frame_arena);
  }

  /** Release arenas **/
  arena_release(scratch_manim_frame_arena);
  arena_release(scratch_cairo_svg_arena);
  arena_release(scratch_string_arena);

  /** Finalize frame count in the blob header **/
  (*out_svg_frames)->num_frames = frame_index;

  fclose(fp);

  timespec_t perf_total_end_time = ts_now();
  double perf_total_time =
      ts_elapsed_sec(perf_total_start_time, perf_total_end_time);
  printf("Manim frontend completed. Total elapsed: %.4f seconds\n",
         perf_total_time);
  printf("Cum surface destroy time: %.4f seconds\n",
         perf_surface_destroy_cum_time);

  return 0;
}
