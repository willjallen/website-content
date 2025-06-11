

#include "common/arena.h"
#include "common/core.h"
#include "ctrs/map.h"
#include "ir/ir.h"

#include <stdio.h>

typedef struct range_t {
  char *start;
  char *end;
  size_t length;
} range_t;

void gen_path_ir(char* svg_path, size_t length) {
  
}

SvgAnimStatus gen_ir_driver(const svg_frames_t *svg_frames) {

  /**
   * For each frame:
   * - Check if svg path id already present, if not generate 'INS' ops otherwise
   * generate mutate ops.
   */

  // map_t data_tag_to_elem_id_map;

  // arena_t *ir_arena = arena_alloc();

  

  for (size_t i = 0; i < svg_frames->num_frames; i++) {

    svg_record_t svg_record = svg_frames->frames[i];
    char *svg_blob = (char *)svg_get_data(svg_frames, i);

    arena_t *svg_path_scratch_arena = arena_alloc();
    
    /**
     * Poor man's svg parser.
     * Single pass. Find '<' tokens, if the next char is 'p' walk to matching
     * '>' token. Record length and copy full <path> obj into scratch svg
     * buffer. Generate ir for this path, then continue.
     */

    bool tracking = false;
    size_t curr_path_len = 0; 
    for (size_t j = 0; j < svg_record.length; j++) {
      if (tracking) {
        ++curr_path_len;
        if (svg_blob[j] == '>') {
          /** Full path found, gen ir **/

          // Add null byte for convenience
          char* dest = arena_push(svg_path_scratch_arena, curr_path_len + 1);
          memcpy(
            dest,
            (void*)&svg_blob[j],
            curr_path_len);
          
          dest[curr_path_len] = '\0';
          
          gen_path_ir(dest, curr_path_len + 1);

          curr_path_len = 0;
          tracking = false;
        }
      } else {
        if (j + 1 < svg_record.length) {
          if (svg_blob[j] == '<' && (svg_blob[j+1] == 'p' || svg_blob[j+1] == 'P')) {
            ++curr_path_len;
            tracking = true;
          }
        }
      }
    }

    // ir_op_t op = {
    //   .op        = IR_OP_SET_ATTR,
    //   .set_attr  = { .element_id = 1234,
    //                  .attribute_type = FILL,
    //                  .attribute_value_str = "red" }
    // };
  }

  return SVG_ANIM_STATUS_SUCCESS;
}
