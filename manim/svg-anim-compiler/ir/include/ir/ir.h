/**
-------------------------------------------------------------------------------
TAG                       PAYLOAD
-------------------------------------------------------------------------------
INS                       (elementId, tagEnum)
                          - Insert a new SVG element of type tagEnum
                          - tagEnum: 0=PATH 1=CIRCLE 2=ELLIPSE 3=RECT ...

DEL                       (elementId)
                          - Permanently remove the element

SET_ATTR                  (elementId, attrId, valueId)
                          - Set one attribute once (e.g. fill, opacity)

SET_STYLE                 (elementId, cssPropId, valueId)
                          - Set one CSS style property (e.g. font-size)

SET_CLASS                 (elementId, classId)
                          - Replace full class attribute with classId

SET_ATTR_RANGE            (attrId, valueId, firstElementId, lastElementId)
                          - Same attr/value applied to a contiguous elementId
range

SET_ATTR_LIST             (attrId, valueId, nIds, elementId[ nIds ])
                          - Same attr/value applied to an arbitrary element list

REWRITE_PATH              (elementId, pathLiteralId)
                          - Replace the path’s ‘d’ data

SET_TRANSFORM             (elementId, m00,m01,m02, m10,m11,m12)
                          - Overwrite full transform matrix

# Analytic / across-frames numeric motions
RANGE_LINEAR              (elementId, attrId, a, b, frameStart, frameEnd)
                          - attr = a*t + b   over given frame span

RANGE_QUADRATIC           (elementId, attrId, a, b, c, frameStart, frameEnd)
                          - attr = a*t² + b*t + c

RANGE_STEP                (elementId, attrId, kRuns, [len,val] × kRuns)
                          - Piece-wise constant run-length list

# Discrete event timelines (scrub-safe)
VIS_TOGGLE_EVENTS         (elementId, nEvents, frame[ nEvents ])
                          - Visibility flips at listed frames

ENUM_EVENTS               (elementId, attrId, nEvents, [frame,state] × nEvents)
                          - Enum/colour/state changes at frames

# Analytic shortcuts
CIRCLE_XY_POLY            (elementId, ax,bx,cx, ay,by,cy, radius)
                          - Center follows two quadratics; radius constant

TRANS_TRANSLATE_LIN       (elementId, ax,bx, ay,by)
                          - translate( ax*t+bx , ay*t+by )

ROTATE_UNIFORM            (elementId, omega, theta0, cx, cy)
                          - rotate( omega*t + theta0 ) around (cx,cy)

SINUSOID_ATTR             (elementId, attrId, A, omega, phi, c)
                          - attr = A*sin( omega*t + phi ) + c

# Structural / grouping
GROUP_BEGIN               (groupId, parentElementId)
GROUP_END                 (groupId)
SET_GROUP_TRANSFORM       (groupId, m00,m01,m02, m10,m11,m12)

# Frame marker
NOP_FRAME                 (none)
                          - Indicates “no changes this frame”
**/

#ifndef IR_H
#define IR_H
#include <stdint.h>

typedef enum ShapeType { PATH, CIRCLE, ELLIPSE, RECT } ShapeType;

typedef enum AttributeType {
    ALIGNMENT_BASELINE,
    WRITING_MODE,
    CLIP,
    CLIP_PATH,
    CLIP_RULE,
    COLOR,
    COLOR_INTERPOLATION,
    COLOR_INTERPOLATION_FILTERS,
    COLOR_RENDERING,
    CURSOR,
    DIRECTION,
    DISPLAY,
    DOMINANT_BASELINE,
    FILL,
    FILL_OPACITY,
    FILL_RULE,
    FILTER,
    FLOOD_COLOR,
    FLOOD_OPACITY,
    FONT_FAMILY,
    FONT_SIZE,
    FONT_SIZE_ADJUST,
    FONT_STRETCH,
    FONT_STYLE,
    FONT_VARIANT,
    FONT_WEIGHT,
    GLYPH_ORIENTATION_HORIZONTAL,
    GLYPH_ORIENTATION_VERTICAL,
    IMAGE_RENDERING,
    BASELINE_SHIFT,
    LIGHTING_COLOR,
    MARKER_END,
    MARKER_MID,
    MARKER_START,
    MASK,
    OPACITY,
    OVERFLOW,
    PAINT_ORDER,
    POINTER_EVENTS,
    SHAPE_RENDERING,
    STOP_COLOR,
    STOP_OPACITY,
    STROKE,
    STROKE_DASHARRAY,
    STROKE_DASHOFFSET,
    STROKE_LINECAP,
    STROKE_LINEJOIN,
    STROKE_MITERLIMIT,
    STROKE_OPACITY,
    STROKE_WIDTH,
    TEXT_ANCHOR,
    TEXT_DECORATION,
    TEXT_RENDERING,
    TRANSFORM,
    UNICODE_BIDI,
    VECTOR_EFFECT,
    VISIBILITY,
    WORD_SPACING,
    LETTER_SPACING
} AttributeType;

typedef struct ir_op_ins_t {
  uint32_t element_id;
  ShapeType shape_type;
} ir_ins_t;

typedef struct ir_op_del_t {
  uint32_t element_id;
} ir_del_t;

typedef struct ir_op_set_attr_t {
  uint32_t element_id;
  AttributeType attribute_type;
  char *attribute_value_str;
} ir_op_set_attr_t;

#endif // IR_H
