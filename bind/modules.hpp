#pragma once

#include <pybind11/pybind11.h>

namespace cnn_compute::bind {

void bind_core(pybind11::module_& module);
void bind_emd(pybind11::module_& module);

} // namespace cnn_compute::bind
