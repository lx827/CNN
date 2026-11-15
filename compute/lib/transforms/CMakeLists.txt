add_library(cnn_compute_transforms STATIC hilbert.cpp)
add_library(CNN::transforms ALIAS cnn_compute_transforms)
set_target_properties(cnn_compute_transforms PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(cnn_compute_transforms PUBLIC CNN::core CNN::envelope CNN::fourier)
