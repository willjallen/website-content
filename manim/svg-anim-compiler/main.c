#include "ir/gen_ir.h"
#include "ir/ir.h"
#include "manim/manim_fe.h"

#include <stdio.h>
int main(const int argc, const char **argv) {
  
    if (argc != 2) {
      fprintf(stderr, "Usage: %s <inDataFile>\n", argv[0]);
      return 1;
    }
  
  const char *in_data_file = argv[1];

  /** Set up arenas **/
  arena_t *svg_frames_blob_arena = arena_alloc();
  arena_t *svg_frames_record_arena = arena_alloc();
  arena_t *ir_arena = arena_alloc();

  // svg_frames will be allocated and pass out by the driver
  svg_frames_t *svg_frames;
  manim_fe_driver(svg_frames_blob_arena, svg_frames_record_arena, in_data_file,
                  &svg_frames);

  ir_op_frames_t *ir_op_frames;
  gen_ir_driver(ir_arena, svg_frames, &ir_op_frames);
  
  return 0;
}

