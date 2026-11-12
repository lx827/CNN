#include "arrays.hpp"
#include "modules.hpp"
#include <emd/api.hpp>
#include <envelope/api.hpp>
#include <interpolation/api.hpp>
#include <pybind11/stl.h>

namespace cnn_compute::bind {
namespace {
    namespace e     = cnn_compute::emd;
    namespace v     = cnn_compute::envelope;
    namespace ip    = cnn_compute::interpolation;
    using RawResult = std::tuple< std::vector< py::array_t< double > >, std::vector< int >, std::string >;

    std::string status_name(e::Status status) {
        switch (status) {
            case e::Status::success: return "success";
            case e::Status::insufficient_extrema: return "insufficient_extrema";
            case e::Status::iteration_limit: return "iteration_limit";
            case e::Status::numerical_failure: return "numerical_failure";
        }
        throw std::logic_error("未知 EMD 状态");
    }
    // 仅检查 Python 布局；有限性与算法前置条件由纯 C++ 公开入口检查一次。
    std::span< const double > vector_view(const ArrayInput &x) {
        if (x.ndim( ) != 1) throw py::value_error("输入必须一维");
        return { x.data( ), static_cast< std::size_t >(x.size( )) };
    }
    RawResult transfer(e::Result &&result) {
        std::vector< py::array_t< double > > columns;
        columns.reserve(result.components.size( ));
        for (auto &component : result.components) columns.push_back(output(std::move(component)));
        return { std::move(columns), std::move(result.iterations), status_name(result.status) };
    }
}    // namespace

void bind_emd_family(py::module_ &module, py::module_ &envelope, py::module_ &interpolation) {
    py::enum_< ip::Method >(interpolation, "Method")
        .value("splrep", ip::Method::splrep)
        .value("pchip", ip::Method::pchip)
        .value("cubic", ip::Method::cubic);
    interpolation.def("interpolate", [](const ArrayInput &x, const ArrayInput &y, const ArrayInput &query, ip::Method method) {
        const auto xv = vector_view(x), yv = vector_view(y), qv = vector_view(query);
        core::Array result;
        { py::gil_scoped_release release; result = ip::interpolate(xv, yv, qv, method); }
        return output(std::move(result)); }, py::arg("x").noconvert( ), py::arg("y").noconvert( ), py::arg("query").noconvert( ), py::arg("method"));
    py::enum_< v::Padding >(envelope, "Padding")
        .value("rilling", v::Padding::rilling)
        .value("numpypad", v::Padding::numpypad);
    py::class_< v::Options >(envelope, "Options")
        .def(py::init<>( ))
        .def_readwrite("interpolation", &v::Options::interpolation)
        .def_readwrite("padding", &v::Options::padding)
        .def_readwrite("pad_width", &v::Options::pad_width)
        .def_readwrite("parabolic_extrema", &v::Options::parabolic_extrema);
    envelope.def("extrema_envelopes", [](const ArrayInput &x, const v::Options &options) -> std::optional< std::tuple< py::array_t< double >, py::array_t< double > > > {
        const auto values = vector_view(x);
        std::optional<v::Envelopes> result;
        { py::gil_scoped_release release; result = v::extrema_envelopes(values, options); }
        if (!result) return std::nullopt;
        return std::make_tuple(output(std::move(result->upper)), output(std::move(result->lower))); }, py::arg("signal").noconvert( ), py::arg("options"));
    envelope.def("combined_envelope", [](const ArrayInput &x, const v::Options &options) -> std::optional< py::array_t< double > > {
        const auto values = vector_view(x);
        std::optional<core::Array> result;
        { py::gil_scoped_release release; result = v::combined_envelope(values, options); }
        if (!result) return std::nullopt;
        return output(std::move(*result)); }, py::arg("signal").noconvert( ), py::arg("options"));
    envelope.def("find_extrema", [](const ArrayInput &x, bool maxima, bool parabolic) {
        const auto values = vector_view(x);
        v::Extrema result;
        { py::gil_scoped_release release; result = v::find_extrema(values, maxima, parabolic); }
        return std::make_tuple(output(std::move(result.locations)), output(std::move(result.values))); }, py::arg("signal").noconvert( ), py::arg("maxima") = true, py::arg("parabolic") = false);
    py::enum_< e::StopMethod >(module, "StopMethod")
        .value("sd", e::StopMethod::sd)
        .value("rilling", e::StopMethod::rilling)
        .value("energy", e::StopMethod::energy)
        .value("fixed", e::StopMethod::fixed);
    py::class_< e::IMFOptions >(module, "IMFOptions")
        .def(py::init<>( ))
        .def_readwrite("env_step_size", &e::IMFOptions::env_step_size)
        .def_readwrite("max_iters", &e::IMFOptions::max_iters)
        .def_readwrite("energy_thresh", &e::IMFOptions::energy_thresh)
        .def_readwrite("stop_method", &e::IMFOptions::stop_method)
        .def_readwrite("sd_thresh", &e::IMFOptions::sd_thresh)
        .def_readwrite("rilling_thresh", &e::IMFOptions::rilling_thresh);
    py::class_< e::Options >(module, "Options")
        .def(py::init<>( ))
        .def_readwrite("imf", &e::Options::imf)
        .def_readwrite("envelope", &e::Options::envelope)
        .def_readwrite("max_imfs", &e::Options::max_imfs)
        .def_readwrite("sift_thresh", &e::Options::sift_thresh)
        .def_readwrite("energy_thresh", &e::Options::energy_thresh)
        .def_readwrite("rilling_thresh", &e::Options::rilling_thresh);
    module.def("get_next_imf", [](const ArrayInput &x, const e::IMFOptions &options, const v::Options &envelope_options) {
        const auto values = vector_view(x);
        e::NextResult result;
        { py::gil_scoped_release release; result = e::get_next_imf(values, options, envelope_options); }
        return std::make_tuple(output(std::move(result.imf)), result.info.continue_flag,
                               result.info.iterations, status_name(result.info.status)); }, py::arg("signal").noconvert( ), py::arg("options"), py::arg("envelope_options"));
    module.def("sift", [](const ArrayInput &x, const e::Options &options) -> RawResult {
        const auto values = vector_view(x);
        e::Result result;
        { py::gil_scoped_release release; result = e::sift(values, options); }
        return transfer(std::move(result)); }, py::arg("signal").noconvert( ), py::arg("options"));
}
}    // namespace cnn_compute::bind
