#pragma once

#include <pybind11/pybind11.h>

namespace cnn_compute::bind {

void bind_core(pybind11::module_& module);
void bind_emd(pybind11::module_& module);
void bind_emd_ensemble(pybind11::module_& module);
void bind_emd_family(pybind11::module_& module, pybind11::module_& envelope,
                     pybind11::module_& interpolation);

} // namespace cnn_compute::bind
