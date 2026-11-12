#include "arrays.hpp"
#include "modules.hpp"
#include <emd/ensemble.hpp>
#include <pybind11/stl.h>

namespace cnn_compute::bind {
namespace {
namespace e = cnn_compute::emd;
using RawResult = std::tuple<std::vector<py::array_t<double>>, std::vector<int>, std::string>;

std::string status_name(e::Status status) {
    switch (status) {
    case e::Status::success: return "success";
    case e::Status::insufficient_extrema: return "insufficient_extrema";
    case e::Status::iteration_limit: return "iteration_limit";
    case e::Status::numerical_failure: return "numerical_failure";
    }
    throw std::logic_error("未知集成筛分状态");
}
RawResult transfer(e::Result&& result) {
    std::vector<py::array_t<double>> columns;
    columns.reserve(result.components.size());
    for (auto& component : result.components)
        columns.push_back(output(std::move(component)));
    return {std::move(columns), std::move(result.iterations), status_name(result.status)};
}

// Python 只检查布局，有限性与参数检查由纯 C++ 公开入口完成。
std::pair<std::span<const double>, std::span<const double>> views(
    const ArrayInput& signal, const ArrayInput& noise, int nensembles) {
    if (signal.ndim() != 1 || noise.ndim() != 2
        || noise.shape(0) != nensembles || noise.shape(1) != signal.size())
        throw py::value_error("输入必须一维，噪声必须为 [nensembles, samples]");
    return {{signal.data(), static_cast<std::size_t>(signal.size())},
            {noise.data(), static_cast<std::size_t>(noise.size())}};
}
} // namespace

void bind_emd_ensemble(py::module_& module) {
    py::enum_<e::NoiseMode>(module, "NoiseMode")
        .value("single", e::NoiseMode::single).value("flip", e::NoiseMode::flip);
    py::class_<e::EnsembleOptions>(module, "EnsembleOptions")
        .def(py::init<>()).def_readwrite("sift", &e::EnsembleOptions::sift)
        .def_readwrite("nensembles", &e::EnsembleOptions::nensembles)
        .def_readwrite("ensemble_noise", &e::EnsembleOptions::ensemble_noise)
        .def_readwrite("noise_mode", &e::EnsembleOptions::noise_mode);
    py::class_<e::CompleteEnsembleOptions>(module, "CompleteEnsembleOptions")
        .def(py::init<>()).def_readwrite("sift", &e::CompleteEnsembleOptions::sift)
        .def_readwrite("nensembles", &e::CompleteEnsembleOptions::nensembles)
        .def_readwrite("ensemble_noise", &e::CompleteEnsembleOptions::ensemble_noise);
    module.def("ensemble_sift", [](const ArrayInput& signal, const ArrayInput& noise,
                                   const e::EnsembleOptions& options) -> RawResult {
        const auto [input, normal] = views(signal, noise, options.nensembles);
        e::Result result;
        { py::gil_scoped_release release; result = e::ensemble_sift(input, normal, options); }
        return transfer(std::move(result));
    }, py::arg("signal").noconvert(), py::arg("normal_noise").noconvert(), py::arg("options"));
    module.def("complete_ensemble_sift", [](const ArrayInput& signal, const ArrayInput& noise,
                                            const e::CompleteEnsembleOptions& options) -> RawResult {
        const auto [input, normal] = views(signal, noise, options.nensembles);
        e::Result result;
        { py::gil_scoped_release release; result = e::complete_ensemble_sift(input, normal, options); }
        return transfer(std::move(result));
    }, py::arg("signal").noconvert(), py::arg("normal_noise").noconvert(), py::arg("options"));
}
} // namespace cnn_compute::bind
