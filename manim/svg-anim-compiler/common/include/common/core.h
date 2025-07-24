#ifndef CORE_H
#define CORE_H

#include "defs.h"
#include "arena.h"
#include <_time.h>
#include <stdlib.h>


/*
 * -----------------------------------------------------------------------------
 *  Status Codes
 * -----------------------------------------------------------------------------
 */

typedef enum SvgAnimStatus {
  SVG_ANIM_STATUS_SUCCESS,
  SVG_ANIM_STATUS_NO_MEMORY,
  SVG_ANIM_STATUS_MALFORMED_SVG
} SvgAnimStatus;

/*
 * -----------------------------------------------------------------------------
 *  SVGs
 * -----------------------------------------------------------------------------
 */

/**
 * @brief Descriptor for an svg within a blob
 */
typedef struct svg_record_t {
  size_t length;
  size_t offset;
} svg_record_t;

/**
 * @brief Sequence of svgs contained within a blob. One svg per frame.
 * @note To read an svg, use \n@code svg_get_data(svg_frames, frame_num)@endcode for
 * convenience
 */
typedef struct svg_frames_t {
  size_t num_frames;
  svg_record_t *frames;
  void *blob;
} svg_frames_t;

/**
 * @brief Returns a pointer to the single associated svg to a given frame.
 * @param svg_frames The structure containing the svg frames blob
 * @param frame_num Frame number to retrieve
 * @return Pointer to the svg for the given frame
 */
static const void *svg_get_data(const svg_frames_t *svg_frames, const size_t frame_num)
{
  return (const unsigned char *)svg_frames->blob + svg_frames->frames[frame_num].offset;
}

/*
 * -----------------------------------------------------------------------------
 *  IR
 * -----------------------------------------------------------------------------
 */



/*
 * -----------------------------------------------------------------------------
 *  Timespec
 * -----------------------------------------------------------------------------
 */

typedef struct timespec timespec_t;

static timespec_t ts_now(void) {
  timespec_t ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts;
}

static double ts_elapsed_sec(const timespec_t start, const timespec_t end) {
  return (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
}

#endif //CORE_H
