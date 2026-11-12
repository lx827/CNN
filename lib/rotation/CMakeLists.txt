add_library(cnn_compute_rotation STATIC rotation.cpp estimation.cpp)
add_library(CNN::rotation ALIAS cnn_compute_rotation)
set_target_properties(cnn_compute_rotation PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(cnn_compute_rotation PUBLIC CNN::core CNN::fourier CNN::transforms CNN::sequence CNN::filtering CNN::numeric)
