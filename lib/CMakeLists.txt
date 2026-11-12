include(FetchContent)

FetchContent_Declare(
    eigen
    URL https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.gz
    URL_HASH SHA256=8586084f71f9bde545ee7fa6d00288b264a2b7ac3607b974e54d13e7162c1c72
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    SOURCE_SUBDIR _headers_only
)
FetchContent_MakeAvailable(eigen)
add_library(cnn_eigen INTERFACE)
add_library(Eigen3::Eigen ALIAS cnn_eigen)
target_include_directories(cnn_eigen SYSTEM INTERFACE "${eigen_SOURCE_DIR}")

set(CNN_COMPUTE_ARCH "baseline")
if(DEFINED ENV{CNN_COMPUTE_ARCH})
    set(CNN_COMPUTE_ARCH "$ENV{CNN_COMPUTE_ARCH}")
endif()
if(NOT CNN_COMPUTE_ARCH MATCHES "^(baseline|avx2)$")
    message(FATAL_ERROR "CNN_COMPUTE_ARCH must be baseline or avx2")
endif()

add_library(cnn_compute_options INTERFACE)
add_library(CNN::options ALIAS cnn_compute_options)
target_compile_features(cnn_compute_options INTERFACE cxx_std_20)
target_compile_definitions(cnn_compute_options INTERFACE EIGEN_DONT_PARALLELIZE)
target_link_libraries(cnn_compute_options INTERFACE Eigen3::Eigen)

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
    target_compile_options(cnn_compute_options INTERFACE ${CNN_COMPUTE_ARCH_FLAGS})
endif()
if(MSVC)
    target_compile_options(cnn_compute_options INTERFACE /utf-8 /EHsc)
    set(CNN_COMPUTE_FP_FLAGS "/fp:strict")
else()
    set(CNN_COMPUTE_FP_FLAGS "-ffp-contract=off")
endif()
target_compile_options(cnn_compute_options INTERFACE ${CNN_COMPUTE_FP_FLAGS})

string(TOUPPER "${CMAKE_BUILD_TYPE}" CNN_BUILD_TYPE_UPPER)
set(CNN_COMPUTE_FLAGS "${CMAKE_CXX_FLAGS} ${CMAKE_CXX_FLAGS_${CNN_BUILD_TYPE_UPPER}} ${CNN_COMPUTE_ARCH_FLAGS} ${CNN_COMPUTE_FP_FLAGS}")

add_subdirectory(core)
add_subdirectory(interpolation)
add_subdirectory(envelope)
add_subdirectory(emd)
install(FILES LICENSE.scipy LICENSE.lapack LICENSE.emd NOTICE.emd DESTINATION cnn_compute/licenses)
