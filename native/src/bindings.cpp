#include <cnn_compute/build_info.hpp>

#include <pybind11/pybind11.h>

namespace py = pybind11;

PYBIND11_MODULE(_native, module) {
    module.doc() = "诊断计算库原生内核与构建信息";
    module.def("build_info", [] {
        const auto info = cnn_compute::build_info();
        py::dict result;
        result["schema"] = cnn_compute::build_info_schema;
        result["compiler_id"] = info.compiler_id;
        result["compiler_version"] = info.compiler_version;
        result["target_arch"] = info.target_arch;
        result["arch_policy"] = info.arch_policy;
        result["compile_options"] = info.compile_options;
        result["simd"] = info.simd;
        result["eigen_version"] = py::make_tuple(info.eigen_major, info.eigen_minor, info.eigen_patch);
        return result;
    });
}
