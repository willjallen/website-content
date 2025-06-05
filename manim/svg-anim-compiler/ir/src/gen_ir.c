

#include "common/core.h"
#include "ctrs/map.h"
#include "ir/ir.h"

#include <stdio.h>

typedef struct range_t {
  char *start;
  char *end;
  size_t length;
} range_t;

SvgAnimStatus gen_ir_driver(const svg_frame_buffers_t *svg_frame_buffers) {

/**
 * For each frame:
 * - Check if svg path id already present, if not generate 'INS' ops otherwise
 * generate mutate ops.
 */

  // map_t data_tag_to_elem_id_map;
  
 for (size_t i = 0; i < svg_frame_buffers->num_frames; i++) {
  buffer_t *svg_frame = &svg_frame_buffers->svg_frames[i];

   // Count total number of <path> elements
   char* curr_blob = svg_frame->data;
   size_t num_paths = 0;
   char* new_blob;
   while ((new_blob = strstr(curr_blob, "<path")) != NULL) {
     ++num_paths;
     curr_blob = new_blob + strlen("<path");

     if (curr_blob > svg_frame->data + svg_frame->size) break;
   }

  if (num_paths <= 0) continue;
   
   // Build string ranges for path
   char *search_pos = svg_frame->data;

   range_t ranges[num_paths];
   for (size_t j = 0; j < num_paths; ++j) {
     // Find the next '<path'
     char *path_start = strstr(search_pos, "<path");
     if (!path_start) break;

     // Find the terminating '>' for this tag
     char *path_end = strchr(path_start, '>');
     if (!path_end) {
       // Malformed SVG – use end of buffer as a fallback
       path_end = svg_frame->data + svg_frame->size;
     }
     ++path_end;                       // include the '>' in the slice

     ranges[j].start  = path_start;
     ranges[j].end    = path_end;
     ranges[j].length = (size_t)(path_end - path_start);

     search_pos = path_end;            // advance search cursor
   }

   for (size_t j = 0; j < num_paths; j++) {
     char tmp[2048];                                 // adjust size as needed
     size_t copy_len = ranges[j].length < sizeof(tmp) - 1 ? ranges[j].length : sizeof(tmp) - 1;
     memcpy(tmp, ranges[j].start, copy_len);
     tmp[copy_len] = '\0';
     printf("%s\n\n", tmp);
   }
   
   // if ()
   // svg_frame->data


   // ir_op_t op = {
   //   .op        = IR_OP_SET_ATTR,
   //   .set_attr  = { .element_id = 1234,
   //                  .attribute_type = FILL,
   //                  .attribute_value_str = "red" }
   // };
   
 } 

 return SVG_ANIM_STATUS_SUCCESS; 
}
