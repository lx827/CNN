#pragma once

#include <core/array.hpp>

namespace cnn_compute::solvers {
// 独立拥有四条带状数组；允许调用者移动交接，返回求解后的 rhs owner。
core::Array solve_tridiagonal(core::Array lower, core::Array diagonal,
                              core::Array upper, core::Array rhs);
}
