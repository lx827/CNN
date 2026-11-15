#pragma once

#include <span>

namespace cnn_compute::solvers::execution {
// n>=2，主对角/rhs长度n，上/下对角长度n-1；缓冲区互不重叠。
// 原地消元，rhs写最终解，下对角复用于第二上对角，无分配。
void solve_tridiagonal(std::span< double > lower, std::span< double > diagonal,
                       std::span< double > upper, std::span< double > rhs);
}    // namespace cnn_compute::solvers::execution
