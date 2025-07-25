#ifndef MAP_H
#define MAP_H
#include <string.h>
#include <stdalign.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include "common/core.h"

/**
 * Hash map takes input uint32_t, hashes it, takes mod <bucket count>, uses
 * probing.
 * Methods:
 * - create
 * - destroy
 * - put
 * - get
 * - remove
 * - _resize
 *
 **/

#define MAP_START_SIZE 64
#define MAP_MAX_LOAD 60


typedef enum BucketState {
  MAP_BUCKET_OCCUPIED,
  MAP_BUCKET_REMOVED,
  MAP_BUCKET_EMPTY
} BucketState;

typedef struct bucket_t {
  uint32_t key;
  BucketState state;

  uint8_t data[];

} bucket_t;

typedef struct map_t {
  size_t size;
  uint32_t count;

  size_t element_size;
  size_t element_align;

  size_t bucket_stride;
  bucket_t *table;

} map_t;
#define MAP_EMPTY_KEY UINT32_MAX

/**
 * Notes:
 * - map->size must be a power of two
 * - element_align must be a power of two
 */
static map_t *map_create(size_t element_size, size_t element_align);
static void map_destroy(map_t *map);
static int map_put(map_t *map, uint32_t key, const void *element);
static int map_get(const map_t *map, const uint32_t key, void *out_element);
static int map_remove(map_t *map, const uint32_t key);
static int _map_resize(map_t *map);
static int _load_ok(const map_t *map);
static bucket_t *_bucket_at(const map_t *map, size_t i);
static bucket_t *_bucket_at_base(uint8_t *base, size_t stride, size_t i);
static uint32_t _map_hash_u32(uint32_t key);
static size_t _next_valid_alignment(size_t a);

static map_t *map_create(const size_t element_size, const size_t element_align) {
  map_t *map = malloc(sizeof(map_t));
  map->size = MAP_START_SIZE;
  map->element_size = element_size;
  map->element_align = element_align;

  map->bucket_stride = ALIGN_UP(sizeof(bucket_t) + element_size, element_align);
  map->table = aligned_alloc(_next_valid_alignment(element_align),
                             map->size * map->bucket_stride);

  for (size_t i = 0; i < map->size; i++) {
    _bucket_at(map, i)->key = MAP_EMPTY_KEY;
    _bucket_at(map, i)->state = MAP_BUCKET_EMPTY;
  }

  return map;
}

static void map_destroy(map_t *map) {
  free(map->table);
  free(map);
}

static int map_put(map_t *map, const uint32_t key, const void *element) {
  if (!_load_ok(map)) {
    if (!_map_resize(map))
      return 0;
  }

  uint32_t hash = _map_hash_u32(key);
  uint32_t idx = hash % map->size;

  size_t i = 0;
  while (true) {
    bucket_t *bucket = _bucket_at(map, idx);

    if (bucket->state == MAP_BUCKET_OCCUPIED && bucket->key == key) {
      memcpy((void *)bucket->data, element, map->element_size);
      return 1;
    }

    if (bucket->key == MAP_EMPTY_KEY) {
      memcpy((void *)bucket->data, element, map->element_size);
      bucket->key = key;
      bucket->state = MAP_BUCKET_OCCUPIED;
      ++map->count;
      return 1;
    }

    if (i == map->size - 1) {
      return 0;
    }

    i += 1;
    idx = (idx + 1) & (map->size - 1);
  }
}

static int map_get(const map_t *map, const uint32_t key, void *out_element) {
  uint32_t hash = _map_hash_u32(key);
  uint32_t idx = hash % map->size;

  while (true) {
    bucket_t *bucket = _bucket_at(map, idx);
    if (bucket->key == key) {
      memcpy(out_element, &bucket->data, map->element_size);
      return 1;
    }

    if (bucket->state == MAP_BUCKET_EMPTY) {
      return 0;
    }

    idx = (idx + 1) & (map->size - 1);
  }
}

static int map_remove(map_t *map, const uint32_t key) {
  uint32_t hash = _map_hash_u32(key);
  uint32_t idx = hash % map->size;

  size_t i = 0;
  while (true) {
    bucket_t *bucket = _bucket_at(map, idx);
    if (bucket->state == MAP_BUCKET_EMPTY)
      return 0;

    if (bucket->state == MAP_BUCKET_OCCUPIED && bucket->key == key) {
      bucket->key = MAP_EMPTY_KEY;
      bucket->state = MAP_BUCKET_REMOVED;
      --map->count;
      return 1;
    }

    if (i == map->size - 1) {
      return 0;
    }

    i += 1;
    idx = (idx + 1) & (map->size - 1);
  }
}

static int _map_resize(map_t *map) {
  const size_t old_map_size = map->size;
  const size_t new_map_size = old_map_size * 2;

  bucket_t *old_table = map->table;
  void *new_table = aligned_alloc(_next_valid_alignment(map->element_align),
                                  new_map_size * map->bucket_stride);

  map->table = new_table;
  map->size = new_map_size;

  for (size_t i = 0; i < map->size; i++) {
    bucket_t *bucket =
        _bucket_at_base((uint8_t *)map->table, map->bucket_stride, i);
    bucket->key = MAP_EMPTY_KEY;
    bucket->state = MAP_BUCKET_EMPTY;
  }

  map->count = 0;
  for (size_t i = 0; i < old_map_size; i++) {
    const bucket_t *bucket =
        _bucket_at_base((uint8_t *)old_table, map->bucket_stride, i);
    if (bucket->key != MAP_EMPTY_KEY) {
      if (!map_put(map, bucket->key, &bucket->data))
        return 0;
    }
  }

  free(old_table);
  return 1;
}

/**
 * Checks if the map load is below MAP_MAX_LOAD
 * @param map self
 * @return 1 if load is acceptable, else 0
 */
static int _load_ok(const map_t *map) {
  return (map->count * 100 / map->size) < MAP_MAX_LOAD;
}

static bucket_t *_bucket_at(const map_t *map, const size_t i) {
  return (bucket_t *)((uint8_t *)map->table + i * map->bucket_stride);
}

static bucket_t *_bucket_at_base(uint8_t *base, const size_t stride,
                               const size_t i) {
  return (bucket_t *)(base + i * stride);
}

static uint32_t _map_hash_u32(uint32_t key) {
  key ^= key >> 16;
  key *= 0x7feb352d;
  key ^= key >> 15;
  key *= 0x846ca68b;
  key ^= key >> 16;
  return key;
}

static size_t _next_valid_alignment(size_t a) {
  a = ALIGN_UP(a, sizeof(void *));
  /* round up to next power of two */
  if (a & (a - 1)) {
    /* count leading zeros, next power of two */
    unsigned shift = sizeof(size_t) * 8 - __builtin_clzll(a);
    a = 1ULL << shift;
  }
  return a;
}

#endif // MAP_H

