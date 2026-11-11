include(FetchContent)

# 依赖只通过 CMake target 传播，不复制头文件或链接本机硬路径。
FetchContent_Declare(
    eigen
    URL https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.gz
    URL_HASH SHA256=8586084f71f9bde545ee7fa6d00288b264a2b7ac3607b974e54d13e7162c1c72
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    # 只取 header-only 基座，跳过上游 BLAS/Fortran、示例与安装规则。
    SOURCE_SUBDIR _headers_only
)
FetchContent_MakeAvailable(eigen)
add_library(cnn_eigen INTERFACE)
add_library(Eigen3::Eigen ALIAS cnn_eigen)
target_include_directories(cnn_eigen SYSTEM INTERFACE "${eigen_SOURCE_DIR}")

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 3.1 CONFIG REQUIRED)

# 固定指令集是可缓存的兼容性契约；默认 x64 基线已由 Eigen 使用 SSE2。
set(CNN_COMPUTE_ARCH "baseline")
if(DEFINED ENV{CNN_COMPUTE_ARCH})
    set(CNN_COMPUTE_ARCH "$ENV{CNN_COMPUTE_ARCH}")
endif()
if(NOT CNN_COMPUTE_ARCH MATCHES "^(baseline|avx2)$")
    message(FATAL_ERROR "CNN_COMPUTE_ARCH must be baseline or avx2")
endif()

add_library(cnn_compute_core STATIC src/build_info.cpp)
add_library(CNN::compute_core ALIAS cnn_compute_core)
set_target_properties(cnn_compute_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_features(cnn_compute_core PUBLIC cxx_std_20)
target_compile_definitions(cnn_compute_core PUBLIC EIGEN_DONT_PARALLELIZE)
target_include_directories(cnn_compute_core PUBLIC include PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
target_link_libraries(cnn_compute_core PUBLIC Eigen3::Eigen)

set(CNN_COMPUTE_ARCH_FLAGS "")
if(CNN_COMPUTE_ARCH STREQUAL "avx2")
    if(NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(AMD64|amd64|x86_64|X86_64)$")
        message(FATAL_ERROR "The avx2 build target requires x86-64")
    endif()
    if(MSVC)
        set(CNN_COMPUTE_ARCH_FLAGS "/arch:AVX2")
    else()
        set(CNN_COMPUTE_ARCH_FLAGS "-mavx2;-mfma")
    endif()
    target_compile_options(cnn_compute_core PUBLIC ${CNN_COMPUTE_ARCH_FLAGS})
endif()
if(MSVC)
    target_compile_options(cnn_compute_core PUBLIC /utf-8 /EHsc)
endif()

string(TOUPPER "${CMAKE_BUILD_TYPE}" CNN_BUILD_TYPE_UPPER)
set(CNN_COMPUTE_FLAGS "${CMAKE_CXX_FLAGS} ${CMAKE_CXX_FLAGS_${CNN_BUILD_TYPE_UPPER}} ${CNN_COMPUTE_ARCH_FLAGS}")
configure_file(build_config.hpp.in build_config.hpp @ONLY)

pybind11_add_module(_native MODULE NO_EXTRAS src/bindings.cpp)
target_link_libraries(_native PRIVATE CNN::compute_core)
install(TARGETS _native LIBRARY DESTINATION cnn_compute RUNTIME DESTINATION cnn_compute)
