#pragma once

#include <core/array.hpp>
#include <span>

namespace cnn_compute::core {

enum class Interpolation { pchip, cubic };

struct Knots {
    Array locations;
    Array values;
};

// 至少两个有限节点，位置严格递增且与值等长；查询有限，顺序任意。
// 首尾段多项式承担外推；不重复检查调用方已保证的输入约束。
Array interpolate(const Knots& points, const Array& query, Interpolation method);
Array pchip(std::span<const double> x, std::span<const double> y, std::span<const double> query);
Array cubic(std::span<const double> x, std::span<const double> y, std::span<const double> query);

} // namespace cnn_compute::core
