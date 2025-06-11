#ifndef CORE_DEFS_H
#define CORE_DEFS_H
/*
* -----------------------------------------------------------------------------
 *  Macros & Defs
 * -----------------------------------------------------------------------------
 */

#define ALIGN_UP(value, alignment)                                             \
(((value) + ((alignment) - 1)) & ~((alignment) - 1))

#if _MSC_VER
#define likely(x) x
#define unlikely(x) x
#else
#define likely(x) __builtin_expect(!!(x), 1)
#define unlikely(x) __builtin_expect(!!(x), 0)
#endif

#endif
