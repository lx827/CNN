add_library(cnn_compute_diagnostic STATIC diagnostic.cpp)
add_library(CNN::diagnostic ALIAS cnn_compute_diagnostic)
set_target_properties(cnn_compute_diagnostic PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(cnn_compute_diagnostic PUBLIC CNN::core CNN::fourier CNN::filtering)
