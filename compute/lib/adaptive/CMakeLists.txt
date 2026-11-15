add_library(cnn_compute_adaptive STATIC adaptive.cpp)
add_library(CNN::adaptive ALIAS cnn_compute_adaptive)
set_target_properties(cnn_compute_adaptive PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(cnn_compute_adaptive PUBLIC CNN::core)
