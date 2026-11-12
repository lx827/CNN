find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 3.1 CONFIG REQUIRED)

pybind11_add_module(_native MODULE NO_EXTRAS module.cpp arrays.cpp core.cpp emd.cpp emd_family.cpp emd_ensemble.cpp)
target_link_libraries(_native PRIVATE CNN::core CNN::emd)

# 导入刚编译的扩展生成声明；只写构建目录，安装时随 wheel 分发。
set(CNN_STUB_DIR "${CMAKE_CURRENT_BINARY_DIR}/stubs")
set(CNN_STUB_IMPORT_DIR "${CMAKE_CURRENT_BINARY_DIR}/python")
file(MAKE_DIRECTORY "${CNN_STUB_IMPORT_DIR}/cnn_compute")
file(WRITE "${CNN_STUB_IMPORT_DIR}/cnn_compute/__init__.py" "")
add_custom_target(cnn_compute_stubs ALL
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different "$<TARGET_FILE:_native>"
            "${CNN_STUB_IMPORT_DIR}/cnn_compute/$<TARGET_FILE_NAME:_native>"
    COMMAND "${CMAKE_COMMAND}" -E env "PYTHONPATH=${CNN_STUB_IMPORT_DIR}"
            "${Python_EXECUTABLE}" -m pybind11_stubgen cnn_compute._native
            --output-dir "${CNN_STUB_DIR}" --numpy-array-use-type-var --exit-code
    DEPENDS _native
    VERBATIM
)
if(SKBUILD_STATE STREQUAL "editable")
    # 平铺 Python 包从源码解析，编辑器需要在源码旁看到原生子模块存根。
    add_custom_command(TARGET cnn_compute_stubs POST_BUILD
        COMMAND "${CMAKE_COMMAND}" -E copy_directory_if_different
                "${CNN_STUB_DIR}/cnn_compute/_native"
                "${PROJECT_SOURCE_DIR}/cnn_compute/_native"
        VERBATIM
    )
endif()
install(TARGETS _native LIBRARY DESTINATION cnn_compute RUNTIME DESTINATION cnn_compute)
install(DIRECTORY "${CNN_STUB_DIR}/cnn_compute/_native" DESTINATION cnn_compute
        FILES_MATCHING PATTERN "*.pyi")
install(FILES "${PROJECT_SOURCE_DIR}/cnn_compute/py.typed" DESTINATION cnn_compute)
