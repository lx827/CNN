# 源码集成与安装分发共用同一批算法 target；只在独立分发时安装。
include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
FetchContent_GetProperties(eigen SOURCE_DIR CNN_EIGEN_SOURCE_DIR)
set(CNN_NATIVE_MODULES core solvers interpolation envelope fourier filtering transforms numeric
    sequence rotation emd wavelet vmd deconvolution ica adaptive diagnostic)
foreach(module IN LISTS CNN_NATIVE_MODULES)
    set(target cnn_compute_${module})
    set_target_properties(${target} PROPERTIES EXPORT_NAME ${module})
    get_target_property(includes ${target} INTERFACE_INCLUDE_DIRECTORIES)
    if(includes)
        set(native_includes)
        foreach(path IN LISTS includes)
            list(APPEND native_includes "$<BUILD_INTERFACE:${path}>")
        endforeach()
        list(APPEND native_includes "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}/cnn_compute>")
        set_property(TARGET ${target} PROPERTY INTERFACE_INCLUDE_DIRECTORIES "${native_includes}")
    endif()
    install(TARGETS ${target} EXPORT CnnComputeTargets ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
endforeach()
# 静态小波库的私有链接依赖必须随导出，vendor 头不安装。
set_target_properties(cnn_compute_pywt PROPERTIES EXPORT_NAME pywt)
set_target_properties(cnn_compute_options PROPERTIES EXPORT_NAME options)
set_target_properties(cnn_eigen PROPERTIES EXPORT_NAME eigen)
set_property(TARGET cnn_eigen PROPERTY INTERFACE_INCLUDE_DIRECTORIES
    "$<BUILD_INTERFACE:${CNN_EIGEN_SOURCE_DIR}>;$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}/cnn_compute/eigen>")
set_property(TARGET cnn_eigen PROPERTY INTERFACE_SYSTEM_INCLUDE_DIRECTORIES
    "$<BUILD_INTERFACE:${CNN_EIGEN_SOURCE_DIR}>;$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}/cnn_compute/eigen>")
install(TARGETS cnn_compute_pywt cnn_compute_options cnn_eigen EXPORT CnnComputeTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(DIRECTORY "${PROJECT_SOURCE_DIR}/lib/" DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/cnn_compute
    FILES_MATCHING PATTERN "*.hpp" PATTERN "vendor" EXCLUDE)
install(DIRECTORY "${CNN_EIGEN_SOURCE_DIR}/Eigen" "${CNN_EIGEN_SOURCE_DIR}/unsupported"
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/cnn_compute/eigen)
install(FILES "${CNN_EIGEN_SOURCE_DIR}/COPYING.MPL2" DESTINATION ${CMAKE_INSTALL_DATADIR}/cnn_compute/licenses
    RENAME LICENSE.eigen)
configure_package_config_file("${PROJECT_SOURCE_DIR}/cmake/CnnComputeConfig.cmake.in"
    "${PROJECT_BINARY_DIR}/CnnComputeConfig.cmake"
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/CnnCompute)
write_basic_package_version_file("${PROJECT_BINARY_DIR}/CnnComputeConfigVersion.cmake"
    VERSION ${PROJECT_VERSION} COMPATIBILITY ExactVersion)
install(EXPORT CnnComputeTargets NAMESPACE CNN:: DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/CnnCompute)
install(FILES "${PROJECT_BINARY_DIR}/CnnComputeConfig.cmake"
    "${PROJECT_BINARY_DIR}/CnnComputeConfigVersion.cmake"
    "${PROJECT_SOURCE_DIR}/cmake/DetectMsvcIncludes.cmake"
    "${PROJECT_SOURCE_DIR}/cmake/msvc_include_probe.ps1"
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/CnnCompute)
