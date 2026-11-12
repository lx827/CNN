#include "arrays.hpp"
#include <emd/mask.hpp>
#include <emd/second_layer.hpp>
#include <transforms/hilbert.hpp>
#include <pybind11/stl.h>

namespace cnn_compute::bind {
namespace {
    namespace e = cnn_compute::emd;
    namespace t = cnn_compute::transforms;
    std::span< const double > vector_view(const ArrayInput &input) {
        if (input.ndim( ) != 1) throw py::value_error("输入必须一维");
        return { input.data( ), static_cast< std::size_t >(input.size( )) };
    }
    const char *status_name(e::Status status) {
        switch (status) {
            case e::Status::success: return "success";
            case e::Status::insufficient_extrema: return "insufficient_extrema";
            case e::Status::iteration_limit: return "iteration_limit";
            case e::Status::numerical_failure: return "numerical_failure";
        }
        throw std::logic_error("未知算法状态");
    }
    auto transfer(e::Result &&value) {
        std::vector< py::array_t< double > > columns;
        columns.reserve(value.components.size( ));
        for (auto &array : value.components) columns.push_back(output(std::move(array)));
        return std::make_tuple(std::move(columns), std::move(value.iterations), std::string(status_name(value.status)));
    }
    auto transfer_mask(e::MaskResult &&value) {
        return std::make_tuple(transfer(std::move(value.decomposition)), output(std::move(value.mask_frequencies)));
    }
    auto transfer_second(e::SecondLayerResult &&value) {
        using Raw = decltype(transfer(e::Result{}));
        std::vector< Raw > layers;
        for (auto &layer : value.layers) layers.push_back(transfer(std::move(layer)));
        return std::make_tuple(std::move(layers), value.output_depth);
    }
    std::vector< std::span< const double > > column_views(const std::vector< ArrayInput > &columns) {
        std::vector< std::span< const double > > result;
        for (const auto &column : columns) result.push_back(vector_view(column));
        return result;
    }
}    // namespace
void bind_emd_mask(py::module_ &module, py::module_ &transforms) {
    py::register_exception< e::MaskConvergenceFailure >(module, "MaskConvergenceFailure");
    py::enum_< e::FirstMask >(module, "FirstMask")
        .value("zc", e::FirstMask::zero_crossings)
        .value("ifrequency", e::FirstMask::instantaneous_frequency)
        .value("explicit_frequency", e::FirstMask::explicit_frequency);
    py::enum_< e::AmplitudeMode >(module, "AmplitudeMode")
        .value("abs", e::AmplitudeMode::absolute)
        .value("ratio_sig", e::AmplitudeMode::ratio_signal)
        .value("ratio_imf", e::AmplitudeMode::ratio_imf);
    py::class_< e::MaskOptions >(module, "MaskOptions")
        .def(py::init<>( ))
        .def_readwrite("imf", &e::MaskOptions::imf)
        .def_readwrite("envelope", &e::MaskOptions::envelope)
        .def_readwrite("mask_freqs", &e::MaskOptions::mask_freqs)
        .def_readwrite("first_mask", &e::MaskOptions::first_mask)
        .def_readwrite("first_frequency", &e::MaskOptions::first_frequency)
        .def_readwrite("mask_amp", &e::MaskOptions::mask_amp)
        .def_readwrite("amp_mode", &e::MaskOptions::amp_mode)
        .def_readwrite("mask_step_factor", &e::MaskOptions::mask_step_factor)
        .def_readwrite("max_imfs", &e::MaskOptions::max_imfs)
        .def_readwrite("nphases", &e::MaskOptions::nphases)
        .def_readwrite("sift_thresh", &e::MaskOptions::sift_thresh);
    py::class_< e::IteratedMaskOptions >(module, "IteratedMaskOptions")
        .def(py::init<>( ))
        .def_readwrite("mask", &e::IteratedMaskOptions::mask)
        .def_readwrite("max_iter", &e::IteratedMaskOptions::max_iter)
        .def_readwrite("averages", &e::IteratedMaskOptions::averages)
        .def_readwrite("iter_thresh", &e::IteratedMaskOptions::iter_thresh)
        .def_readwrite("sample_rate", &e::IteratedMaskOptions::sample_rate)
        .def_readwrite("weight_power", &e::IteratedMaskOptions::weight_power)
        .def_readwrite("weighted", &e::IteratedMaskOptions::weighted)
        .def_readwrite("exclude_edges", &e::IteratedMaskOptions::exclude_edges);
    module.def("get_next_imf_mask", [](const ArrayInput &signal, double frequency, double amplitude, int nphases, const e::IMFOptions &imf, const envelope::Options &envelope) {
        const auto input = vector_view(signal);
        e::NextResult result;
        { py::gil_scoped_release release; result = e::get_next_imf_mask(input, frequency, amplitude, nphases, imf, envelope); }
        return std::make_tuple(output(std::move(result.imf)), result.info.continue_flag,
                               result.info.iterations, std::string(status_name(result.info.status))); }, py::arg("signal").noconvert( ), py::arg("frequency"), py::arg("amplitude"), py::arg("nphases"), py::arg("imf"), py::arg("envelope"));
    module.def("get_mask_frequency", [](const ArrayInput &signal, e::FirstMask method, double first, const e::IMFOptions &imf) {
        const auto input = vector_view(signal);
        py::gil_scoped_release release;
        return e::get_mask_frequency(input, method, first, imf); }, py::arg("signal").noconvert( ), py::arg("method"), py::arg("first"), py::arg("imf"));
    module.def("mask_sift", [](const ArrayInput &signal, const e::MaskOptions &options) {
        const auto input = vector_view(signal);
        e::MaskResult result;
        { py::gil_scoped_release release; result = e::mask_sift(input, options); }
        return transfer_mask(std::move(result)); }, py::arg("signal").noconvert( ), py::arg("options"));
    module.def("iterated_mask_sift", [](const ArrayInput &signal, const e::IteratedMaskOptions &options) {
        const auto input = vector_view(signal);
        e::IteratedMaskResult result;
        { py::gil_scoped_release release; result = e::iterated_mask_sift(input, options); }
        return std::make_tuple(transfer_mask(std::move(result.result)), output(std::move(result.mask_variability)),
                               result.iterations, result.converged); }, py::arg("signal").noconvert( ), py::arg("options"));
    module.def("sift_second_layer", [](const std::vector< ArrayInput > &columns, const e::Options &options) {
        const auto inputs = column_views(columns);
        e::SecondLayerResult result;
        { py::gil_scoped_release release; result = e::sift_second_layer(inputs, options); }
        return transfer_second(std::move(result)); }, py::arg("columns"), py::arg("options"));
    module.def("mask_sift_second_layer", [](const std::vector< ArrayInput > &columns, const ArrayInput &frequencies, const e::MaskOptions &options) {
        const auto inputs = column_views(columns);
        const auto masks = vector_view(frequencies);
        e::SecondLayerResult result;
        { py::gil_scoped_release release; result = e::mask_sift_second_layer(inputs, masks, options); }
        return transfer_second(std::move(result)); }, py::arg("columns"), py::arg("frequencies").noconvert( ), py::arg("options"));
    transforms.def("analytic_signal", [](const ArrayInput &signal) {
        const auto input = vector_view(signal);
        std::vector<std::complex<double>> result;
        { py::gil_scoped_release release; result = t::analytic_signal(input); }
        auto* owner = new std::vector<std::complex<double>>(std::move(result));
        py::capsule capsule(owner, [](void* value) { delete static_cast<std::vector<std::complex<double>>*>(value); });
        return py::array_t<std::complex<double>>({static_cast<py::ssize_t>(owner->size())},
            {sizeof(std::complex<double>)}, owner->data(), capsule); }, py::arg("signal").noconvert( ));
    transforms.def("amplitude_normalise", [](const ArrayInput &signal) {
        const auto input = vector_view(signal);
        core::Array result;
        { py::gil_scoped_release release; result = t::amplitude_normalise(input); }
        return output(std::move(result)); }, py::arg("signal").noconvert( ));
    transforms.def("frequency_transform", [](const ArrayInput &signal, double sample_rate, bool normalised, int smooth_phase, int smooth_frequency) {
        const auto input = vector_view(signal);
        t::FrequencyResult result;
        { py::gil_scoped_release release; result = t::frequency_transform(input, sample_rate, normalised, smooth_phase, smooth_frequency); }
        return std::make_tuple(output(std::move(result.phase)), output(std::move(result.frequency)),
                               output(std::move(result.amplitude))); }, py::arg("signal").noconvert( ), py::arg("sample_rate"), py::arg("normalised"), py::arg("smooth_phase"), py::arg("smooth_frequency"));
}
}    // namespace cnn_compute::bind
