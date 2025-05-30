#ifndef CORE_H
#define CORE_H

#if _MSC_VER
#define likely(x) x
#define unlikely(x) x
#else
#define likely(x) __builtin_expect(!!(x), 1)
#define unlikely(x) __builtin_expect(!!(x), 0)
#endif
#include <stdbool.h>
#include <stddef.h>

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

typedef struct svg_frame_buffers_t {
  size_t num_frames;
  buffer_t *svg_frames;
} svg_frame_buffers_t;

#endif //CORE_H
