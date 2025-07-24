

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


/**
 * @brief Descriptor for an token within a blob
 */
typedef struct token_pair_record_t {
  size_t key_length;
  size_t key_offset;
  size_t value_length;
  size_t value_offset;
} token_pair_record_t;

/**
 * @brief Sequence of svgs contained within a blob
 * @note To read an svg, use \n@code svg_get_data(svg_frames, i)@endcode for
 * convenience
 */
typedef struct token_pair_buffer_t {
  size_t num_pairs;
  token_pair_record_t *token_pairs;
  void *blob;
} token_pair_buffer_t;

static const void *token_get_key(const token_pair_buffer_t *buffer, const size_t i)
{
  return (const unsigned char *)buffer->blob + buffer->token_pairs[i].key_offset;
}

static const void *token_get_value(const token_pair_buffer_t *buffer, const size_t i)
{
  return (const unsigned char *)buffer->blob + buffer->token_pairs[i].value_offset;
}

void tokenize_path(arena_t token_stack_area, char* svg_path, size_t num_tokens) {
  /** Each token is of the form "x"="y". Termination is at > */
  
  
}

void gen_path_ir(arena_t *token_record_scratch_arena,
  arena_t *token_blob_scratch_arena,
  arena_t *ir_arena, char* svg_path, size_t length) {

  // Initialize the token_pair_buffer
  // token_pair_buffer_t *token_pair_buffer = arena_push_struct(token_blob_scratch_arena, token_pair_buffer_t);
  
  
  // ir_op_t op = {
  //   .op        = IR_OP_SET_ATTR,
  //   .set_attr  = { .element_id = 1234,
  //                  .attribute_type = FILL,
  //                  .attribute_value_str = "red" }
  // };
  
}

SvgAnimStatus gen_ir_driver(arena_t *ir_arena, const svg_frames_t *svg_frames, ir_op_frames_t **ir_op_frames) {

  /**
   * For each frame:
   * - Check if svg path id already present, if not generate 'INS' ops otherwise
   * generate mutate ops.
   */

  // map_t data_tag_to_elem_id_map;

  // arena_t *ir_arena = arena_alloc();
  arena_t *scratch_arena = arena_alloc();

  
  arena_t *svg_path_scratch_arena = arena_alloc();

  for (size_t i = 0; i < svg_frames->num_frames; i++) {

    svg_record_t svg_record = svg_frames->frames[i];
    char *svg_blob = (char *)svg_get_data(svg_frames, i);
    
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
          curr_path_len += 1;
          
            gen_path_ir(scratch_arena, scratch_arena, ir_arena, dest, curr_path_len);

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
  }

  return SVG_ANIM_STATUS_SUCCESS;
}
