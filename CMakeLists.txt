cmake_minimum_required(VERSION 3.28)
if(CMAKE_HOST_WIN32 AND NOT DEFINED CMAKE_CXX_COMPILER)
    set(CMAKE_CXX_COMPILER cl)
endif()
project(cnn_compute VERSION 0.1.0 LANGUAGES CXX)
if(WIN32 AND NOT MSVC)
    message(FATAL_ERROR "Windows builds require MSVC; run uv sync through vsdev")
endif()
if(MSVC)
    # /showIncludes 前缀按编译器实际输出字节传给 Ninja。CMake 的自动代码页
    # 解码可能损坏中文前缀，漏掉间接头依赖，进而混入旧工作区布局的对象。
    set(CNN_INCLUDE_PROBE "${CMAKE_CURRENT_BINARY_DIR}/cnn_include_probe")
    file(WRITE "${CNN_INCLUDE_PROBE}.hpp" "#pragma once\n")
    file(WRITE "${CNN_INCLUDE_PROBE}.cpp" "#include \"${CNN_INCLUDE_PROBE}.hpp\"\n")
    execute_process(
        COMMAND "${CMAKE_CXX_COMPILER}" /nologo /showIncludes /c
                "${CNN_INCLUDE_PROBE}.cpp" "/Fo${CNN_INCLUDE_PROBE}.obj"
        OUTPUT_VARIABLE CNN_INCLUDE_OUTPUT ERROR_VARIABLE CNN_INCLUDE_ERROR
        ENCODING NONE COMMAND_ERROR_IS_FATAL ANY
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
add_subdirectory(bind)

option(CNN_COMPUTE_BUILD_TESTS "Build native C++ interface contract tests" OFF)
if(CNN_COMPUTE_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests/native)
endif()
