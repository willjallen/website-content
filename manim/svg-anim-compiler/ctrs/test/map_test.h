/*=============================================================================
  map_tests.h — validation & micro-benchmarks for map.h
  ---------------------------------------------------------------------------
  Usage:
      #define MAP_TEST_MAIN        // <- optional: gives you a main() driver
      #include "map_tests.h"

      $ cc -O3 -std=c11 map_tests.c -o map_tests
      $ ./map_tests
=============================================================================*/
#ifndef MAP_TESTS_H
#define MAP_TESTS_H

#include "ctrs/map.h"
#include "common/core.h"

#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* ---------------------------------------------------------------------------
   Tunables
   ------------------------------------------------------------------------ */
#ifndef MAP_TEST_ITERATIONS /* items used in stress / perf tests    */
#define MAP_TEST_ITERATIONS (1u << 20) /* 1 048 576 */
#endif

/* ---------------------------------------------------------------------------
   Lightweight RNG (xorshift32) – faster and better spread than rand()
   ------------------------------------------------------------------------ */
static inline uint32_t prng_next(uint32_t *state) {
  uint32_t x = *state;
  x ^= x << 13;
  x ^= x >> 17;
  x ^= x << 5;
  return *state = x;
}

/* ---------------------------------------------------------------------------
   Test 1: basic CRUD
   ------------------------------------------------------------------------ */
static void map_test_basic(void) {
  puts("[basic]");

  map_t *m = map_create(sizeof(uint64_t), alignof(uint64_t));

  const uint64_t value = 0xdeadbeefcafebabeULL;
  assert(map_put(m, 42u, &value) == 1);

  uint64_t readback = 0;
  assert(map_get(m, 42u, &readback) == 1);
  assert(readback == value);

  assert(map_remove(m, 42u) == 1);
  assert(map_get(m, 42u, &readback) == 0); /* gone */

  map_destroy(m);
}

/* ---------------------------------------------------------------------------
   Test 2: resize & load-factor
   ------------------------------------------------------------------------ */
static void map_test_resize(void) {
  puts("[resize / load]");

  map_t *m = map_create(sizeof(uint32_t), alignof(uint32_t));
  size_t original_size = m->size;

  uint32_t payload = 0;
  uint32_t key = 0;
  /* push well past 60 % – we go to 90 % to be sure a resize occurs       */
  size_t target = (size_t)(original_size * 0.9);

  for (size_t i = 0; i < target; ++i) {
    key = i * 2654435761u; /* Knuth multiplicative mix */
    payload = ~key;
    assert(map_put(m, key, &payload));
  }

  assert(m->size > original_size); /* must have doubled at least once      */

  /* full scan to ensure every key is retrievable after rehash            */
  for (size_t i = 0; i < target; ++i) {
    key = i * 2654435761u;
    assert(map_get(m, key, &payload));
    assert(payload == ~key);
  }

  map_destroy(m);
}

/* ---------------------------------------------------------------------------
   Test 3: stress + micro-benchmarks
   ------------------------------------------------------------------------ */
static void map_test_perf(size_t count) {
  printf("[perf] %lu items\n", count);

  map_t *m = map_create(sizeof(uint32_t), alignof(uint32_t));

  uint32_t *keys = malloc(count * sizeof(uint32_t));
  uint32_t *vals = malloc(count * sizeof(uint32_t));
  if (!keys || !vals) {
    fputs("out of memory\n", stderr);
    exit(EXIT_FAILURE);
  }

  /* generate deterministic pseudo-random workload                       */
  uint32_t rng = 1u;
  for (size_t i = 0; i < count; ++i) {
    keys[i] = prng_next(&rng);
    vals[i] = ~keys[i];
  }

  /* 1) bulk insert ----------------------------------------------------- */
  timespec_t t0 = ts_now();
  for (size_t i = 0; i < count; ++i)
    map_put(m, keys[i], &vals[i]);
  struct timespec t1 = ts_now();

  /* 2) read-back ------------------------------------------------------- */
  uint32_t tmp;
  for (size_t i = 0; i < count; ++i)
    assert(map_get(m, keys[i], &tmp) && tmp == vals[i]);
  timespec_t t2 = ts_now();

  /* 3) removals -------------------------------------------------------- */
  for (size_t i = 0; i < count; ++i)
    assert(map_remove(m, keys[i]) == 1);
  timespec_t t3 = ts_now();

  /* ------------------------------------------------------------------- */
  double ins_s = ts_elapsed_sec(t0, t1);
  double get_s = ts_elapsed_sec(t1, t2);
  double rem_s = ts_elapsed_sec(t2, t3);

  printf("  insert : %.2f Mops/s  (%.1f ns/op)\n", (count / ins_s) / 1e6,
         (ins_s * 1e9) / count);
  printf("  lookup : %.2f Mops/s  (%.1f ns/op)\n", (count / get_s) / 1e6,
         (get_s * 1e9) / count);
  printf("  remove : %.2f Mops/s  (%.1f ns/op)\n", (count / rem_s) / 1e6,
         (rem_s * 1e9) / count);

  free(keys);
  free(vals);
  map_destroy(m);
}

/* ---------------------------------------------------------------------------
   Public driver – call this from your unit-test harness or enable the
   MAP_TEST_MAIN block below.
   ------------------------------------------------------------------------ */
static inline void map_tests_run_all(void) {
  map_test_basic();
  map_test_resize();
  map_test_perf(MAP_TEST_ITERATIONS);
  puts("all map tests passed");
}

/* ---------------------------------------------------------------------------
   Optional standalone runner
   ------------------------------------------------------------------------ */
#ifdef MAP_TEST_MAIN
int main(void) {
  map_tests_run_all();
  return 0;
}
#endif /* MAP_TEST_MAIN */

#endif /* MAP_TESTS_H */
