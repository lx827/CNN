include(FetchContent)
FetchContent_Declare(pocketfft
    URL https://github.com/mreineck/pocketfft/archive/4d865cba24359b05b37da4e75aee24498c3b78e7.tar.gz
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    SOURCE_SUBDIR _headers_only)
FetchContent_MakeAvailable(pocketfft)
add_library(cnn_compute_fourier STATIC fourier.cpp)
add_library(CNN::fourier ALIAS cnn_compute_fourier)
target_include_directories(cnn_compute_fourier PUBLIC "${PROJECT_SOURCE_DIR}/lib")
target_include_directories(cnn_compute_fourier SYSTEM PRIVATE "${pocketfft_SOURCE_DIR}")
target_compile_definitions(cnn_compute_fourier PRIVATE POCKETFFT_NO_MULTITHREADING)
target_link_libraries(cnn_compute_fourier PUBLIC CNN::options CNN::core)
set_target_properties(cnn_compute_fourier PROPERTIES POSITION_INDEPENDENT_CODE ON)
install(FILES "${pocketfft_SOURCE_DIR}/LICENSE.md" DESTINATION cnn_compute/licenses RENAME LICENSE.pocketfft)
