#ifndef ARENA_H
#define ARENA_H
#include <stddef.h>
#include <stdlib.h>

#if defined(__APPLE__) || defined(__unix__)
#include <unistd.h>
#include <sys/mman.h>
#endif
#ifdef _WIN64
#include <windows.h>
#endif

#include "common/core.h"

#include <assert.h>

#define ARENA_VIRTUAL_ALLOC_DEFAULT_SIZE 8ULL << 30 // 8 GB

typedef struct arena_t {
    unsigned char *base;  /* start of reserved range    */
    size_t capacity;      /* bytes reserved (virtual)   */
    size_t committed;     /* bytes with R/W access      */
    size_t pos;           /* bytes currently in use     */
    size_t page_size;       /* OS page size (cached)      */
} arena_t;

/**
 * @brief Allocate and initialize a new memory arena.
 *
 * The arena reserves an initial contiguous memory block with a default
 * 8 GB virtual allocation All subsequent arena_* allocators carve out pieces
 * of this block in stack‑like fashion. Call arena_release() to free everything.
 *
 * @return Pointer to a newly created arena, or NULL on allocation failure.
 */
static arena_t *arena_alloc(void);

/**
 * @brief Allocate and initialize a new memory arena.
 *
 * The arena reserves an initial contiguous memory block with size
 * virtual_upper_bound. All subsequent arena_* allocators carve out pieces of
 * this block in stack‑like fashion. Call arena_release() to free everything.
 *
 * @param virtual_upper_bound Size of virtual allocation.
 *
 * @return Pointer to a newly created arena, or NULL on allocation failure.
 */
static arena_t *arena_alloc_spec(size_t virtual_upper_bound);

/**
 * @brief Release all memory owned by an arena and destroy it.
 *
 * @param arena Pointer returned by arena_alloc().
 */
static void arena_release(arena_t *arena);

/**
 * @brief Allocate an uninitialized block from the arena.
 *
 * Allocation is O(1). The block is valid until the arena is cleared
 * or rewound past its position.
 *
 * @param arena Arena to allocate from.
 * @param size  Number of bytes requested.
 * @return Pointer to the start of the block, or NULL if out of space.
 */
static void *arena_push(arena_t *arena, size_t size);

/**
 * @brief Allocate a zero‑initialised block from the arena.
 *
 * Same semantics as arena_push() but the returned memory is cleared to 0.
 * 
 * @param arena Arena to allocate from.
 * @param size  Number of bytes requested.
 * @return Pointer to the start of the block, or NULL if out of space.
 */
static void *arena_push_zero(arena_t *arena, size_t size);

#define arena_push_array(arena, type, count) \
        (type *)arena_push((arena), sizeof(type) * (count))

#define arena_push_array_zero(arena, type, count) \
        (type *)arena_push_zero((arena), sizeof(type) * (count))

#define arena_push_struct(arena, type) \
        push_array((arena), type, 1)

#define arena_push_struct_zero(arena, type) \
        push_array_zero((arena), type, 1)

/**
 * @brief Pop bytes off the arena "stack".
 *
 * Effectively rewinds the current position by @p size bytes.
 * Passing a @p size greater than the current position is undefined.
 * 
 * @param arena Arena to pop from.
 * @param size  Number of bytes to pop.
 */
static void arena_pop(arena_t *arena, size_t size);

/**
 * @brief Get the current position (size in use) of the arena.
 * 
 * @param arena Arena in use.
 */
static size_t arena_get_pos(arena_t *arena);

/**
 * @brief Rewind the arena to a previously saved position.
 * 
 * @param arena Arena to set position to.
 * @param pos Value previously obtained from arena_get_pos().
 */
static void arena_set_pos_back(arena_t *arena, size_t pos);

/**
 * @brief Clear the arena without releasing its backing memory.
 *
 * @param arena Arena to clear.
 */
static void arena_clear(arena_t *arena);

//*******************************************//


static arena_t *arena_alloc(void) {
  return arena_alloc_spec(ARENA_VIRTUAL_ALLOC_DEFAULT_SIZE);
}

static arena_t *arena_alloc_spec(const size_t virtual_upper_bound) {
  arena_t *arena = malloc(sizeof(arena_t));
  if (!arena)
    return NULL;

  arena->page_size = (size_t)getpagesize();
  arena->capacity = ALIGN_UP(virtual_upper_bound, arena->page_size);

  /* Reserve contiguous address range with no access */
  arena->base =
      mmap(NULL, arena->capacity, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);

  if (arena->base == MAP_FAILED) {
    free(arena);
    return NULL;
  }

  /* Commit first page */
  if (mprotect(arena->base, arena->page_size, PROT_READ | PROT_WRITE) != 0) {
    munmap(arena->base, arena->capacity);
    free(arena);
    return NULL;
  }

  arena->committed = arena->page_size;
  arena->pos = 0;

  return arena;
}

static void arena_release(arena_t *arena) {
  munmap(arena->base, arena->capacity);
  free(arena);
}

static void *arena_push(arena_t *arena, size_t size) {
  size_t new_pos = arena->pos + size;
  if (new_pos > arena->capacity)
    return NULL;

  if (new_pos > arena->committed) {
    const size_t new_commit = ALIGN_UP(new_pos, arena->page_size);
    const size_t to_commit = new_commit - arena->committed;

    if (mprotect(arena->base + arena->committed, to_commit,
                 PROT_READ | PROT_WRITE) != 0)
      return NULL;

    arena->committed = new_commit;
  }

  void* ptr = arena->base + arena->pos;
  arena->pos = new_pos;
  return ptr;
}

static void arena_pop(arena_t *arena, size_t size) {
  assert(size <= arena->pos);
  arena->pos -= size;
}

static void arena_clear(arena_t *arena) {
  arena_pop(arena, arena->pos);
}

#endif
