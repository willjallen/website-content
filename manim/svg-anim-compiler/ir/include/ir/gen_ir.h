#ifndef GEN_IR_H
#define GEN_IR_H
#include "common/core.h"
#include "ir/ir.h"
SvgAnimStatus gen_ir_driver(arena_t *ir_arena, const svg_frames_t *svg_frames, ir_op_frames_t **ir_op_frames);
#endif // GEN_IR_H
