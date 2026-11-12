#pragma once

#include <core/array.hpp>

namespace cnn_compute::solvers {
// n>=2，主对角/rhs长n、上下对角长n-1；独立拥有四条带状数组。
// 允许调用者移动交接，返回求解后的 rhs owner。
core::Array solve_tridiagonal(core::Array lower, core::Array diagonal,
                              core::Array upper, core::Array rhs);
}    // namespace cnn_compute::solvers
