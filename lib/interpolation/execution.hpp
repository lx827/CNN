#pragma once

#include <interpolation/api.hpp>
#include <vector>

namespace cnn_compute::interpolation {

// 按最大节点/查询规模准备容量；同一活跃调用独占，可连续复用。
struct Workspace {
    core::Array h, slope, derivative, diagonal, lower, upper, rhs;
    core::Array coefficients, knots, band, fit_rhs;
    void prepare(std::size_t nodes, std::size_t queries);
};

namespace execution {
// 所有前置条件由公开边界建立；out 与输入/工作区不重叠，长度等于 query。
// 不保存借用输入；工作区中的系数会在下次调用被覆盖。
void interpolate(std::span<const double> x, std::span<const double> y,
                 std::span<const double> query, std::span<double> out,
                 Method method, Workspace& workspace);
}
} // namespace cnn_compute::interpolation
