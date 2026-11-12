#pragma once

#include <interpolation/api.hpp>
#include <optional>
#include <span>

namespace cnn_compute::envelope {

enum class Padding { rilling, numpypad };
struct Options {
    interpolation::Method interpolation = interpolation::Method::splrep;
    Padding padding = Padding::rilling;
    int pad_width = 2;
    bool parabolic_extrema = false;
};
struct Envelopes { core::Array upper, lower; };
struct Extrema { core::Array locations, values; };

// 严格局部极值；平台不是极值。调用方提供有限信号，少于三点返回空。
// 输出独立拥有存储；原语按此前提直接比较，不额外扫描输入。
Extrema find_extrema(std::span<const double> signal, bool maxima = true,
                     bool parabolic = false);
// 对齐 emd 0.8.1 的极值插值包络；极值不足返回 nullopt。
std::optional<Envelopes> extrema_envelopes(std::span<const double> signal,
                                         const Options& options = {});
// 单侧极大值插值包络；结果独立拥有，不计算或分配下包络结果。
std::optional<core::Array> upper_envelope(std::span<const double> signal,
                                         const Options& options = {});
// abs(signal) 的极大值构成单条包络；仅 numpypad 组合有定义。
std::optional<core::Array> combined_envelope(std::span<const double> signal,
                                           const Options& options);

} // namespace cnn_compute::envelope
