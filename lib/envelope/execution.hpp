#pragma once

#include <envelope/api.hpp>
#include <interpolation/execution.hpp>
#include <vector>
#include <utility>

namespace cnn_compute::envelope {

struct Workspace {
    std::vector<std::ptrdiff_t> maxima, minima, left_max, left_min, right_max, right_min;
    std::vector<double> max_x, max_y, min_x, min_y;
    std::vector<double> pad_left, pad_right;
    core::Array query;
    interpolation::Workspace interpolation;
    void prepare(std::size_t samples, std::size_t padding);
};
namespace execution {
// out 与输入/工作区不重叠；两条输出各有 signal.size() 个元素。
// workspace 可重用，所有借用在同步调用返回时结束；false 仅表示极值不足。
bool extrema_envelopes(std::span<const double> signal, std::span<double> upper,
                       std::span<double> lower, const Options& options,
                       Workspace& workspace);
bool combined_envelope(std::span<const double> signal, std::span<double> output,
                       const Options& options, Workspace& workspace);
std::pair<std::size_t, std::size_t> count_extrema(std::span<const double> signal);
}
} // namespace cnn_compute::envelope
