find_package(Threads REQUIRED)
add_executable(cnn_compute_emd_contract emd_contract.cpp)
target_link_libraries(cnn_compute_emd_contract PRIVATE CNN::emd Threads::Threads)
add_test(NAME emd_native_contract COMMAND cnn_compute_emd_contract)
