cmake_minimum_required(VERSION 3.28)
# Windows 始终使用已初始化的 MSVC，避免 PATH 上的 MinGW 被意外选中。
if(CMAKE_HOST_WIN32 AND NOT DEFINED CMAKE_CXX_COMPILER)
    set(CMAKE_CXX_COMPILER cl)
endif()
project(cnn_compute VERSION 0.1.0 LANGUAGES CXX)
if(WIN32 AND NOT MSVC)
    message(FATAL_ERROR "Windows builds require MSVC; run uv sync through vsdev")
endif()

add_subdirectory(native)
