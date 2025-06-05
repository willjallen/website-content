#ifndef CORE_H
#define CORE_H

#if _MSC_VER
#define likely(x) x
#define unlikely(x) x
#else
#define likely(x) __builtin_expect(!!(x), 1)
#define unlikely(x) __builtin_expect(!!(x), 0)
#endif
#include <_time.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>


#define ALIGN_UP(value, alignment)                                             \
(((value) + ((alignment) - 1)) & ~((alignment) - 1))

typedef enum SvgAnimStatus { SVG_ANIM_STATUS_SUCCESS, SVG_ANIM_STATUS_NO_MEMORY } SvgAnimStatus;

typedef struct buffer_t {
  char *data;
  size_t size;
  size_t capacity;
} buffer_t;

inline static void init_buffer(buffer_t *buffer) {
  buffer->size = 0;
  buffer->capacity = 0;
  buffer->data = NULL;
}


inline static SvgAnimStatus buffer_writer(void *closure, const void *data, const size_t length) {
  buffer_t *buffer = closure;

  if (!length)
    return SVG_ANIM_STATUS_SUCCESS;

  const size_t needed = buffer->size + length;
  
  if (needed > buffer->capacity) {
    size_t new_capacity = buffer->capacity ? buffer->capacity * 2 : 1024;

    while (new_capacity < needed) {
      if (new_capacity > SIZE_MAX / 2) {
        return SVG_ANIM_STATUS_NO_MEMORY;
      }
      new_capacity *= 2;
    }

    void *new_data = realloc(buffer->data, new_capacity);
    if (!new_data)
      return SVG_ANIM_STATUS_NO_MEMORY;

    buffer->data = new_data;
    buffer->capacity = new_capacity;
  }

  memcpy((unsigned char *)buffer->data + buffer->size, data, length);
  buffer->size += length;

  return SVG_ANIM_STATUS_SUCCESS;
}

typedef struct svg_frame_buffers_t {
  size_t num_frames;
  buffer_t *svg_frames;
} svg_frame_buffers_t;

typedef struct ir_frame_buffers_t {
  size_t num_frames;
  buffer_t *ir_frames;
} ir_frame_buffers_t;


typedef struct timespec timespec;

static inline timespec ts_now(void) {
  timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts;
}

static inline double ts_elapsed_sec(const timespec start, const timespec end) {
  return (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
}

#endif //CORE_H
