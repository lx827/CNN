#pragma once

#include <pybind11/pybind11.h>

namespace cnn_compute::bind {

void bind_core(pybind11::module_ &module);
void bind_numeric(pybind11::module_ &module);
void bind_rotation(pybind11::module_ &module);
void bind_wavelet(pybind11::module_ &module);
void bind_vmd(pybind11::module_ &module);
void bind_diagnostic(pybind11::module_ &module);
void bind_emd(pybind11::module_ &module);
void bind_emd_ensemble(pybind11::module_ &module);
void bind_emd_family(pybind11::module_ &module, pybind11::module_ &envelope,
                     pybind11::module_ &interpolation);
void bind_emd_mask(pybind11::module_ &module, pybind11::module_ &transforms);

}    // namespace cnn_compute::bind
