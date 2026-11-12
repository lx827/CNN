#include "arrays.hpp"
#include "modules.hpp"
#include <emd/emd.hpp>
#include <pybind11/stl.h>

#include <cmath>

namespace cnn_compute::bind {
namespace {

using SiftOutput = std::optional<std::tuple<py::array_t<double>, int, bool>>;
using EnvelopeOutput = std::optional<std::tuple<py::array_t<double>, py::array_t<double>>>;

core::Interpolation interpolation(const std::string& value) {
    if (value == "pchip") return core::Interpolation::pchip;
    if (value == "cubic") return core::Interpolation::cubic;
    throw py::value_error("包络插值只支持 pchip 或 cubic");
}
void validate_rilling(const std::array<double, 3>& thresholds) {
    const auto [first, second, fraction] = thresholds;
    if (!std::isfinite(first) || !std::isfinite(second) || !std::isfinite(fraction)
        || first <= 0.0 || second < first || fraction < 0.0 || fraction > 1.0)
        throw py::value_error("Rilling 阈值必须满足 0 < sd1 <= sd2, 0 <= fraction <= 1");
}
SiftOutput run_sift(std::span<const double> values, const cnn_compute::emd::SiftParameters& parameters) {
    std::optional<cnn_compute::emd::SiftResult> result;
    {
        py::gil_scoped_release release;
        result = cnn_compute::emd::sift(values, parameters);
    }
    if (!result) return std::nullopt;
    return std::make_tuple(output(std::move(result->imf)), result->iterations, result->converged);
}
} // namespace

void bind_emd(py::module_& module) {
    module.def("sift_pchip_sd", [](const ArrayInput& array, int max_sifts, int mirror_extrema, double sd_threshold) -> SiftOutput {
        const auto values = input(array, 8);
        if (max_sifts <= 0 || mirror_extrema <= 0 || !std::isfinite(sd_threshold) || sd_threshold <= 0.0)
            throw py::value_error("筛分参数必须为正且有限");
        return run_sift(values, {max_sifts, mirror_extrema, sd_threshold});
    }, py::arg("signal").noconvert(), py::arg("max_sifts"), py::arg("mirror_extrema"), py::arg("sd_threshold"));
    module.def("sift_imf", [](const ArrayInput& array, int max_sifts, int mirror_extrema,
                             double sd_threshold, const std::string& method,
                             const std::string& rule, const std::array<double, 3>& thresholds) -> SiftOutput {
        const auto values = input(array, 8);
        if (max_sifts <= 0 || mirror_extrema <= 0 || !std::isfinite(sd_threshold) || sd_threshold <= 0.0)
            throw py::value_error("筛分参数必须为正且有限");
        cnn_compute::emd::SiftParameters parameters{max_sifts, mirror_extrema, sd_threshold};
        parameters.interpolation = interpolation(method);
        if (rule == "sd") parameters.stopping_rule = cnn_compute::emd::StoppingRule::sd;
        else if (rule == "rilling") parameters.stopping_rule = cnn_compute::emd::StoppingRule::rilling;
        else throw py::value_error("停止准则只支持 sd 或 rilling");
        validate_rilling(thresholds);
        parameters.rilling_thresholds = thresholds;
        return run_sift(values, parameters);
    }, py::arg("signal").noconvert(), py::arg("max_sifts"), py::arg("mirror_extrema"),
       py::arg("sd_threshold"), py::arg("interpolation"), py::arg("stopping_rule"), py::arg("rilling_thresholds"));
    module.def("_envelopes_pchip", [](const ArrayInput& array, int mirror_extrema) -> EnvelopeOutput {
        const auto values = input(array, 8);
        if (mirror_extrema <= 0) throw py::value_error("镜像宽度必须为正");
        std::optional<cnn_compute::emd::Envelopes> result;
        {
            py::gil_scoped_release release;
            result = cnn_compute::emd::envelopes(values, mirror_extrema);
        }
        if (!result) return std::nullopt;
        return std::make_tuple(output(std::move(result->upper)), output(std::move(result->lower)));
    }, py::arg("signal").noconvert(), py::arg("mirror_extrema"));
    module.def("_envelopes", [](const ArrayInput& array, int mirror_extrema, const std::string& method) -> EnvelopeOutput {
        const auto values = input(array, 8);
        if (mirror_extrema <= 0) throw py::value_error("镜像宽度必须为正");
        const auto selected = interpolation(method);
        std::optional<cnn_compute::emd::Envelopes> result;
        {
            py::gil_scoped_release release;
            result = cnn_compute::emd::envelopes(values, mirror_extrema, selected);
        }
        if (!result) return std::nullopt;
        return std::make_tuple(output(std::move(result->upper)), output(std::move(result->lower)));
    }, py::arg("signal").noconvert(), py::arg("mirror_extrema"), py::arg("interpolation"));
    module.def("_rilling_stop", [](const ArrayInput& upper, const ArrayInput& lower,
                                  const std::array<double, 3>& thresholds) {
        const auto high = input(upper, 1), low = input(lower, 1);
        if (high.size() != low.size()) throw py::value_error("上下包络必须等长");
        validate_rilling(thresholds);
        py::gil_scoped_release release;
        return cnn_compute::emd::rilling_stop(high, low, thresholds);
    }, py::arg("upper").noconvert(), py::arg("lower").noconvert(), py::arg("thresholds"));
}

} // namespace cnn_compute::bind
