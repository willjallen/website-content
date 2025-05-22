cmake_minimum_required(VERSION 3.31)

project(svgAnimCompiler LANGUAGES C)

add_executable(svgAnimCompiler main.c
        ctrs/map.h
        ctrs/map_test.h)


# -----------------------------------------------------------------------------
#  Cairo
# -----------------------------------------------------------------------------
include(FetchContent)
include(ExternalProject)


# -----------------------------------------------------------------------------
#  Native Cairo discovery (uses CMake's FindCairo which delegates to pkg‑config)
# -----------------------------------------------------------------------------
find_package(Cairo QUIET)
if(TARGET Cairo::Cairo)
    # Provide a uniform target name so the rest of the script can keep using
    # `cairo::cairo` regardless of how the library was located.
    add_library(cairo::cairo ALIAS Cairo::Cairo)
    set(CAIRO_FOUND TRUE)
endif()

find_package(PkgConfig QUIET)

option(USE_SYSTEM_CAIRO "Prefer a cairo already on the system" ON)

if(USE_SYSTEM_CAIRO AND PKG_CONFIG_FOUND)
    pkg_check_modules(CAIRO IMPORTED_TARGET cairo)
    if(CAIRO_FOUND AND TARGET PkgConfig::CAIRO AND NOT TARGET cairo::cairo)
        # Provide a uniform target name for the rest of the script
        add_library(cairo::cairo ALIAS PkgConfig::CAIRO)
    endif()
endif()

# On Windows, try vcpkg’s CMake config before giving up
if(NOT CAIRO_FOUND AND WIN32)
    find_package(cairo CONFIG QUIET)
    if(TARGET cairo::cairo)
        set(CAIRO_FOUND TRUE)
    endif()
endif()

if(NOT CAIRO_FOUND)
    message(STATUS "cairo not found, building from source (Meson)")

    set(_cairo_install ${CMAKE_BINARY_DIR}/cairo-install)

    file(MAKE_DIRECTORY
        ${_cairo_install}/include
        ${_cairo_install}/include/cairo
        ${_cairo_install}/lib)

    set(_cairo_src   ${CMAKE_BINARY_DIR}/cairo_ep-src)
    set(_cairo_build ${CMAKE_BINARY_DIR}/cairo_ep-build)

    ExternalProject_Add(cairo_ep
        GIT_REPOSITORY https://gitlab.freedesktop.org/cairo/cairo.git
        GIT_TAG        1.18.0
        UPDATE_COMMAND ""
        SOURCE_DIR     ${_cairo_src}
        BINARY_DIR     ${_cairo_build}

        CONFIGURE_COMMAND
            meson setup ${_cairo_src} ${_cairo_build}
                        --prefix ${_cairo_install}
                        -Ddefault_library=shared
                        -Dbuildtype=release

        BUILD_COMMAND     meson compile  -C ${_cairo_build}
        INSTALL_COMMAND   meson install  -C ${_cairo_build}

        BUILD_BYPRODUCTS
            ${_cairo_install}/lib/${CMAKE_STATIC_LIBRARY_PREFIX}cairo${CMAKE_STATIC_LIBRARY_SUFFIX}
    )

    add_library(cairo::cairo STATIC IMPORTED GLOBAL)
set_target_properties(cairo::cairo PROPERTIES
    IMPORTED_IMPLIB "${_cairo_install}/lib/libcairo.dll.a"  # stub for linker
    IMPORTED_LOCATION "${_cairo_install}/bin/libcairo-2.dll" # the real DLL
    INTERFACE_INCLUDE_DIRECTORIES "${_cairo_install}/include/cairo"
)
    add_dependencies(cairo::cairo cairo_ep)

endif()

target_link_libraries(svgAnimCompiler PRIVATE cairo::cairo)


# -----------------------------------------------------------------------------
#  Warnings
# -----------------------------------------------------------------------------

if(MSVC)
    target_compile_options(svgAnimCompiler PRIVATE
            /W4            # highest warning level
            /WX            # warnings as errors
            /permissive-   # stricter standard conformance
    )
else()  # GCC / Clang
    target_compile_options(svgAnimCompiler PRIVATE
            -Wall -Wextra -Wpedantic -Werror -Wno-error=unused-function
    )
endif()

# -----------------------------------------------------------------------------
#  Symbols
# -----------------------------------------------------------------------------

if(CMAKE_CXX_COMPILER_ID MATCHES "MSVC")
   target_compile_options(${TARGET_NAME} PRIVATE /Zi)

   # Tell linker to include symbol data
    set_target_properties(${TARGET_NAME} PROPERTIES 
        LINK_FLAGS "/INCREMENTAL:NO /DEBUG /OPT:REF /OPT:ICF"
    )

    # Set file name & location
    set_target_properties(${TARGET_NAME} PROPERTIES 
        COMPILE_PDB_NAME ${TARGET_NAME} 
        COMPILE_PDB_OUTPUT_DIR ${CMAKE_BINARY_DIR}
    )
endif()
