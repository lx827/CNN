add_library(cnn_compute_sequence STATIC sequence.cpp)
add_library(CNN::sequence ALIAS cnn_compute_sequence)
set_target_properties(cnn_compute_sequence PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(cnn_compute_sequence PUBLIC CNN::core)
