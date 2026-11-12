#pragma once

#include <emd/emd.hpp>
#include <emd/extrema.hpp>

namespace cnn_compute::emd::detail {

// 保持筛分循环复用极值工作区，包络插值交给公共 core。
std::optional< Envelopes > make_envelopes(const Array &signal, int width, Workspace &workspace,
                                          Interpolation method);

}    // namespace cnn_compute::emd::detail
