#include "manim/manim_fe.h"

#include <stdio.h>
int main(const int argc, const char **argv) {
  
    if (argc != 2) {
      fprintf(stderr, "Usage: %s <inDataFile>\n", argv[0]);
      return 1;
    }
  
  const char *in_data_file = argv[1];
  printf("Reading from: %s\n", in_data_file);

  svg_frame_buffers_t svg_frame_buffers;
  manim_fe_driver(in_data_file, &svg_frame_buffers);
  
  return 0;
}

