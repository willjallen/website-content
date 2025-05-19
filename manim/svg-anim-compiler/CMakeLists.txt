cmake_minimum_required(VERSION 3.16)

project(svgAnimCompiler LANGUAGES C)

add_executable(svgAnimCompiler main.c)


if(MSVC)
    target_compile_options(svgAnimCompiler PRIVATE
            /W4            # highest warning level
            /WX            # warnings as errors
            /permissive-   # stricter standard conformance
    )
else()  # GCC / Clang
    target_compile_options(svgAnimCompiler PRIVATE
            -Wall -Wextra -Wpedantic -Werror
    )
endif()

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
