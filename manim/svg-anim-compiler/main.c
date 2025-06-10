#include "manim/manim_fe.h"
#include "ir/gen_ir.h"

#include <stdio.h>
int main(const int argc, const char **argv) {
  
    if (argc != 2) {
      fprintf(stderr, "Usage: %s <inDataFile>\n", argv[0]);
      return 1;
    }
  
  const char *in_data_file = argv[1];

  svg_frame_buffers_t svg_frame_buffers;
  manim_fe_driver(in_data_file, &svg_frame_buffers);
  gen_ir_driver(&svg_frame_buffers);
  
  return 0;
}

