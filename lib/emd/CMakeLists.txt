add_library(cnn_compute_emd STATIC extrema.cpp envelopes.cpp stopping.cpp sift.cpp decomposition.cpp
            ensemble.cpp mask.cpp second_layer.cpp)
add_library(CNN::emd ALIAS cnn_compute_emd)
set_target_properties(cnn_compute_emd PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(cnn_compute_emd PUBLIC CNN::core CNN::envelope CNN::interpolation CNN::transforms)
