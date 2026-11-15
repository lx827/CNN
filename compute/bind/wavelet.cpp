#include "arrays.hpp"
#include <wavelet/api.hpp>
#include <pybind11/stl.h>

namespace cnn_compute::bind {
namespace {
    struct CoefficientSet {
        wavelet::Plan         plan;
        wavelet::Coefficients coefficients;
        CoefficientSet(const std::string &name, const std::string &mode) : plan(name, mode) {}
    };
    std::span< const double > signal_view(const ArrayInput &array) {
        if (array.ndim( ) != 1) throw py::value_error("小波输入必须是一维");
        return { array.data( ), static_cast< std::size_t >(array.size( )) };
    }
}    // namespace
void bind_wavelet(py::module_ &parent) {
    auto module = parent.def_submodule("wavelet", "原生 DWT/WP 与阈值去噪");
    py::class_< CoefficientSet, std::shared_ptr< CoefficientSet > >(module, "CoefficientSet")
        .def_property_readonly("coefficients", [](const std::shared_ptr< CoefficientSet > &self) {
            py::tuple arrays(self->coefficients.bands.size( ));
            for (std::size_t i = 0; i < self->coefficients.bands.size( ); ++i) {
                const auto           &band = self->coefficients.bands[i];
                py::array_t< double > array({ band.size( ) }, { sizeof(double) }, band.data( ), py::cast(self));
                array.attr("flags").attr("writeable") = false;
                arrays[i]                             = std::move(array);
            }
            return arrays;
        })
        .def("reconstruct", [](const CoefficientSet &self, const std::vector< std::size_t > &selected) {
            core::Array result;
            {
                py::gil_scoped_release release;
                result = wavelet::reconstruct_selected(self.coefficients, self.plan, selected);
            }
            return output(std::move(result)); }, py::arg("selected"));
    module.def("analyze_coefficients", [](const ArrayInput &array, const std::string &name, int level, const std::string &mode, bool packet) {
        const auto values = signal_view(array);
        auto result = std::make_shared<CoefficientSet>(name, mode);
        {
            py::gil_scoped_release release;
            result->coefficients = wavelet::decompose(values, result->plan, level, packet);
        }
        return result; }, py::arg("signal").noconvert( ), py::arg("wavelet"), py::arg("level"), py::arg("mode"), py::arg("packet"));
    module.def("decompose", [](const ArrayInput &array, const std::string &name, int level, const std::string &mode, bool packet) {
        const auto values = signal_view(array);
        wavelet::Coefficients coefficients;
        std::vector<core::Array> reconstructed;
        {
            py::gil_scoped_release release;
            const wavelet::Plan plan(name, mode);
            coefficients = wavelet::decompose(values, plan, level, packet);
            reconstructed = wavelet::reconstruct_components(coefficients, plan);
        }
        py::tuple bands(coefficients.bands.size()), signals(reconstructed.size());
        for (std::size_t i = 0; i < reconstructed.size(); ++i) {
            bands[i] = output(std::move(coefficients.bands[i]));
            signals[i] = output(std::move(reconstructed[i]));
        }
        return py::make_tuple(bands, signals); }, py::arg("signal").noconvert( ), py::arg("wavelet"), py::arg("level"), py::arg("mode"), py::arg("packet"));
    module.def("denoise", [](const ArrayInput &array, const std::string &name, int level, const std::string &mode, double scale) {
        const auto values = signal_view(array);
        core::Array result;
        {
            py::gil_scoped_release release;
            result = wavelet::denoise(values, wavelet::Plan(name, "symmetric"), level, mode, scale);
        }
        return output(std::move(result)); }, py::arg("signal").noconvert( ), py::arg("wavelet"), py::arg("level"), py::arg("threshold_mode"), py::arg("threshold_scale"));
}
}    // namespace cnn_compute::bind
