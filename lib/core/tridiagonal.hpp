#pragma once

#include <core/array.hpp>

namespace cnn_compute::core {

// 调用方拥有四条带状数组；消元在其缓冲区上进行，节点数至少为 4。
Array solve_tridiagonal(Array lower, Array diagonal,
                                Array upper, Array rhs);

}  // namespace cnn_compute::core
