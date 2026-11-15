#pragma once

#include <emd/emd.hpp>
#include <emd/extrema.hpp>
#include <span>

namespace cnn_compute::emd::detail {

// 上下包络借用 workspace 缓冲，在下次 make_envelopes 或工作区销毁前有效。
struct EnvelopeSpans {
    std::span< const double > upper, lower;
};

// 极值定位、镜像延拓与插值执行全部复用 workspace；包络直接写入其缓冲。
// 极值不足返回空；数值产生非有限包络时抛错。
std::optional< EnvelopeSpans > make_envelopes(const Array &signal, int width, Workspace &workspace,
                                              Interpolation method);

}    // namespace cnn_compute::emd::detail
