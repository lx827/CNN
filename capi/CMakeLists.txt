add_library(cnn_compute_c SHARED basic.cpp decomposition.cpp analysis.cpp fourier_plan.cpp filtering_plan.cpp result.cpp)
add_library(CNN::c ALIAS cnn_compute_c)
target_compile_definitions(cnn_compute_c PRIVATE CNN_COMPUTE_C_EXPORTS)
if(MSVC)
    target_compile_options(cnn_compute_c INTERFACE /utf-8)
endif()
target_include_directories(cnn_compute_c PUBLIC
    "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
    "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>")
target_link_libraries(cnn_compute_c PRIVATE CNN::numeric CNN::sequence CNN::rotation CNN::emd
    CNN::wavelet CNN::vmd CNN::deconvolution CNN::ica CNN::adaptive CNN::diagnostic)
set_target_properties(cnn_compute_c PROPERTIES EXPORT_NAME c CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES OUTPUT_NAME cnn_compute)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    target_link_options(cnn_compute_c PRIVATE "LINKER:--exclude-libs,ALL")
endif()
install(TARGETS cnn_compute_c EXPORT CnnComputeTargets
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(FILES include/cnn_compute.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
