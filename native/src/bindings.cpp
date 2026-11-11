#include <cnn_compute/build_info.hpp>
#include <cnn_compute/emd.hpp>

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <cmath>
#include <memory>

namespace py = pybind11;

namespace {
using ArrayInput = py::array_t<double, py::array::c_style>;
std::span<const double> input(const ArrayInput& array, py::ssize_t minimum) {
    if (array.ndim() != 1 || array.size() < minimum)
        throw py::value_error("输入必须是一维且满足最小长度");
    const auto values = std::span<const double>(array.data(), array.size());
    for (const double value : values)
        if (!std::isfinite(value)) throw py::value_error("输入必须全部有限");
    return values;
}
py::array output(cnn_compute::emd::Array&& values) {
    auto owner = std::make_unique<cnn_compute::emd::Array>(std::move(values));
    auto* ptr = owner.get();
    py::capsule capsule(ptr, [](void* value) {
        delete static_cast<cnn_compute::emd::Array*>(value);
    });
    owner.release();
    return py::array(py::dtype::of<double>(), {ptr->size()}, {sizeof(double)}, ptr->data(), capsule);
}
} // namespace

PYBIND11_MODULE(_native, module) {
    module.doc() = "诊断计算库原生内核与构建信息";
    module.def("sift_pchip_sd", [](const ArrayInput& array, int max_sifts, int mirror_extrema, double sd_threshold) -> py::object {
        const auto values = input(array, 8);
        if (max_sifts <= 0 || mirror_extrema <= 0 || !std::isfinite(sd_threshold) || sd_threshold <= 0.0)
            throw py::value_error("筛分参数必须为正且有限");
        std::optional<cnn_compute::emd::SiftResult> result;
        {
            py::gil_scoped_release release;
            result = cnn_compute::emd::sift(values, {max_sifts, mirror_extrema, sd_threshold});
        }
        if (!result) return py::none();
        return py::make_tuple(output(std::move(result->imf)), result->iterations, result->converged);
    }, py::arg("signal").noconvert(), py::arg("max_sifts"), py::arg("mirror_extrema"), py::arg("sd_threshold"));
    module.def("_envelopes_pchip", [](const ArrayInput& array, int mirror_extrema) -> py::object {
        const auto values = input(array, 8);
        if (mirror_extrema <= 0) throw py::value_error("镜像宽度必须为正");
        std::optional<cnn_compute::emd::Envelopes> result;
        {
            py::gil_scoped_release release;
            result = cnn_compute::emd::envelopes(values, mirror_extrema);
        }
        if (!result) return py::none();
        return py::make_tuple(output(std::move(result->upper)), output(std::move(result->lower)));
    }, py::arg("signal").noconvert(), py::arg("mirror_extrema"));
    module.def("_pchip", [](const ArrayInput& x, const ArrayInput& y, const ArrayInput& query) {
        const auto nodes = input(x, 2), values = input(y, 2), coordinates = input(query, 1);
        if (nodes.size() != values.size()) throw py::value_error("节点与值必须等长");
        for (std::size_t i = 1; i < nodes.size(); ++i)
            if (nodes[i] <= nodes[i - 1]) throw py::value_error("节点必须严格递增");
        cnn_compute::emd::Array result;
        {
            py::gil_scoped_release release;
            result = cnn_compute::emd::pchip(nodes, values, coordinates);
        }
        return output(std::move(result));
    }, py::arg("x").noconvert(), py::arg("y").noconvert(), py::arg("query").noconvert());
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
