#include "arrays.hpp"
#include "modules.hpp"
#include <emd/family.hpp>
#include <pybind11/stl.h>

namespace cnn_compute::bind {
namespace {
    namespace family = emd::family;
    py::object reason(family::Reason value) {
        switch (value) {
            case family::Reason::none: return py::none( );
            case family::Reason::zero_variance: return py::str("zero_variance");
            case family::Reason::insufficient_extrema: return py::str("insufficient_extrema");
            case family::Reason::no_valid_ensemble_member: return py::str("no_valid_ensemble_member");
            case family::Reason::maximum_sifts_reached: return py::str("maximum_sifts_reached");
        }
        throw std::logic_error("未知 EMD 结果状态");
    }
}    // namespace

void bind_emd_business(py::module_ &module) {
    py::enum_< family::Method >(module, "FamilyMethod")
        .value("emd", family::Method::emd)
        .value("eemd", family::Method::eemd)
        .value("ceemdan", family::Method::ceemdan);
    py::enum_< core::Interpolation >(module, "FamilyInterpolation")
        .value("pchip", core::Interpolation::pchip)
        .value("cubic", core::Interpolation::cubic);
    py::enum_< emd::StoppingRule >(module, "FamilyStoppingRule")
        .value("sd", emd::StoppingRule::sd)
        .value("rilling", emd::StoppingRule::rilling);
    py::class_< emd::SiftParameters >(module, "FamilySiftParameters")
        .def(py::init([] { return emd::SiftParameters{ 100, 3, .2 }; }))
        .def_readwrite("max_sifts", &emd::SiftParameters::max_sifts)
        .def_readwrite("mirror_extrema", &emd::SiftParameters::mirror_extrema)
        .def_readwrite("sd_threshold", &emd::SiftParameters::sd_threshold)
        .def_readwrite("interpolation", &emd::SiftParameters::interpolation)
        .def_readwrite("stopping_rule", &emd::SiftParameters::stopping_rule)
        .def_readwrite("rilling_thresholds", &emd::SiftParameters::rilling_thresholds);
    py::class_< family::Options >(module, "FamilyOptions")
        .def(py::init<>( ))
        .def_readwrite("sift", &family::Options::sift)
        .def_readwrite("max_imfs", &family::Options::max_imfs)
        .def_readwrite("ensemble_size", &family::Options::ensemble_size)
        .def_readwrite("noise_scale", &family::Options::noise_scale);
    module.def("decompose", [](const ArrayInput &signal, family::Method method, const family::Options &options, const std::vector< std::uint32_t > &seed) {
        if (signal.ndim() != 1) throw py::value_error("EMD 输入必须是一维");
        family::Result result;
        {
            py::gil_scoped_release release;
            result = family::decompose({signal.data(), static_cast<std::size_t>(signal.size())}, method, options, seed);
        }
        py::tuple imfs(result.imfs.size());
        for (std::size_t i = 0; i < result.imfs.size(); ++i) imfs[i] = output(std::move(result.imfs[i]));
        return py::make_tuple(imfs, output(std::move(result.residual)), result.iterations,
                              result.converged, reason(result.reason)); }, py::arg("signal").noconvert( ), py::arg("method"), py::arg("options"), py::arg("seed"));
}
}    // namespace cnn_compute::bind
