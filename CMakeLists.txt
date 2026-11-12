cmake_minimum_required(VERSION 3.28)
if(CMAKE_HOST_WIN32 AND NOT DEFINED CMAKE_CXX_COMPILER)
    set(CMAKE_CXX_COMPILER cl)
endif()
project(cnn_compute VERSION 0.1.0 LANGUAGES CXX)
option(CNN_COMPUTE_BUILD_PYTHON "Build Python bindings" ${SKBUILD})
if(CNN_COMPUTE_BUILD_PYTHON)
    set(CNN_SHARED_DEFAULT OFF)
else()
    set(CNN_SHARED_DEFAULT ON)
endif()
option(CNN_COMPUTE_BUILD_SHARED "Build the C ABI shared library" ${CNN_SHARED_DEFAULT})
if(WIN32 AND NOT MSVC)
    message(FATAL_ERROR "Windows builds require MSVC; run uv sync through vsdev")
endif()
if(MSVC AND NOT CNN_COMPUTE_BUILD_PYTHON)
    # 独立库固定编译器诊断语言，让 Ninja 识别依赖前缀，不使用 Python 探针。
    set(CMAKE_CXX_COMPILER_LAUNCHER "${CMAKE_COMMAND};-E;env;VSLANG=1033")
    set(CMAKE_C_COMPILER_LAUNCHER "${CMAKE_COMMAND};-E;env;VSLANG=1033")
    set(CMAKE_CXX_CL_SHOWINCLUDES_PREFIX "Note: including file: ")
    set(CMAKE_CL_SHOWINCLUDES_PREFIX "Note: including file: ")
endif()
if(MSVC AND CNN_COMPUTE_BUILD_PYTHON)
    # CMake 内部字符串必须是 UTF-8；Ninja 生成器再按控制台代码页输出规则。
    # /showIncludes 的原始 GBK 字节不能直接写入前缀，也不能按系统 ANSI
    # 代码页解码 UTF-8 控制台输出，否则会漏生成规则或丢失间接头依赖。
    find_package(Python REQUIRED COMPONENTS Interpreter)
    set(CNN_INCLUDE_PROBE "${CMAKE_CURRENT_BINARY_DIR}/cnn_include_probe")
    file(WRITE "${CNN_INCLUDE_PROBE}.hpp" "#pragma once\n")
    file(WRITE "${CNN_INCLUDE_PROBE}.cpp" "#include \"${CNN_INCLUDE_PROBE}.hpp\"\n")
    execute_process(
        COMMAND "${Python_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/bind/msvc_output.py"
                "${CMAKE_CXX_COMPILER}" /nologo /showIncludes /c
                "${CNN_INCLUDE_PROBE}.cpp" "/Fo${CNN_INCLUDE_PROBE}.obj"
        OUTPUT_VARIABLE CNN_INCLUDE_OUTPUT ERROR_VARIABLE CNN_INCLUDE_ERROR
        ENCODING UTF-8 COMMAND_ERROR_IS_FATAL ANY
    )
    string(REPLACE "\\" "/" CNN_INCLUDE_OUTPUT "${CNN_INCLUDE_OUTPUT}${CNN_INCLUDE_ERROR}")
    string(REPLACE "\n" ";" CNN_INCLUDE_LINES "${CNN_INCLUDE_OUTPUT}")
    foreach(CNN_INCLUDE_LINE IN LISTS CNN_INCLUDE_LINES)
        if(CNN_INCLUDE_LINE MATCHES "cnn_include_probe.hpp")
            string(REGEX REPLACE "[A-Za-z]:/.*$" "" CNN_INCLUDE_PREFIX "${CNN_INCLUDE_LINE}")
            string(STRIP "${CNN_INCLUDE_PREFIX}" CNN_INCLUDE_PREFIX)
            set(CMAKE_CXX_CL_SHOWINCLUDES_PREFIX "${CNN_INCLUDE_PREFIX} ")
            set(CMAKE_CL_SHOWINCLUDES_PREFIX "${CNN_INCLUDE_PREFIX} ")
        endif()
    endforeach()
endif()

add_subdirectory(lib)
if(CNN_COMPUTE_BUILD_PYTHON)
    add_subdirectory(bind)
endif()

option(CNN_COMPUTE_BUILD_TESTS "Build native C++ interface contract tests" OFF)
if(CNN_COMPUTE_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests/native)
endif()
