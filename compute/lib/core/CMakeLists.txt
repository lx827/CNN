add_library(cnn_compute_core STATIC build_info.cpp)
add_library(CNN::core ALIAS cnn_compute_core)
set_target_properties(cnn_compute_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(cnn_compute_core PUBLIC "${PROJECT_SOURCE_DIR}/lib"
                           PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
target_link_libraries(cnn_compute_core PUBLIC CNN::options)

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/build_config.hpp.in
               ${CMAKE_CURRENT_BINARY_DIR}/build_config.hpp @ONLY)
set_property(SOURCE build_info.cpp APPEND PROPERTY OBJECT_DEPENDS "${CMAKE_CURRENT_BINARY_DIR}/build_config.hpp")
