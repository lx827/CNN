#pragma once

#include <core/interpolation.hpp>
#include <vector>

namespace cnn_compute::emd::detail {

using core::Array;
using Extrema = core::Knots;

struct Workspace {
    Array                                   difference, left, center, right, denominator, shift, refined;
    Eigen::Array< bool, Eigen::Dynamic, 1 > maxima, minima;
    std::vector< Eigen::Index >             max_indices, min_indices;
};

// 工作区由一次筛分持有，在各轮极值检测与精化之间复用。
void    locate(const Array &signal, Workspace &workspace);
Extrema refine(const Array &signal, const std::vector< Eigen::Index > &indices, Workspace &work);
Extrema mirror(const Extrema &extrema, double left_axis, double right_axis, int width);

}    // namespace cnn_compute::emd::detail
