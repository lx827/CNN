#include "arrays.hpp"
#include <vmd/api.hpp>
#include <pybind11/stl.h>

namespace cnn_compute::bind {
void bind_vmd(py::module_& parent) {
    auto module = parent.def_submodule("vmd", "单边工作区 ADMM VMD");
    module.def("decompose", [](const ArrayInput& array, double fs, int modes, double alpha,
                               double tau, double tolerance, int iterations, bool dc,
                               std::size_t max_samples, int initialization, std::uint64_t seed) {
        if (array.ndim() != 1) throw py::value_error("VMD 输入必须是一维");
        const auto values = std::span<const double>(array.data(), array.size());
        vmd::Result result;
        {
            py::gil_scoped_release release;
            result = vmd::decompose(values, fs, {modes, alpha, tau, tolerance, iterations, dc,
                                                max_samples, initialization, seed});
        }
        return py::make_tuple(output(std::move(result.modes)), output(std::move(result.center_frequencies_hz)),
                              output(std::move(result.center_frequency_history_hz)), output(std::move(result.residual)),
                              result.valid_length, result.iterations, result.converged, result.status, result.reason);
    }, py::arg("signal").noconvert(), py::arg("sample_rate_hz"), py::arg("modes"), py::arg("alpha"),
       py::arg("tau"), py::arg("tolerance"), py::arg("max_iterations"), py::arg("dc"),
       py::arg("max_samples"), py::arg("initialization"), py::arg("seed"));
}
}
