add_library(cnn_compute_ica STATIC ica.cpp)
add_library(CNN::ica ALIAS cnn_compute_ica)
set_target_properties(cnn_compute_ica PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(cnn_compute_ica PUBLIC CNN::core)
