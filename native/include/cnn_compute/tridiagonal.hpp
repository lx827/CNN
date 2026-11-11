#pragma once

#include <Eigen/Core>

namespace cnn_compute::emd {

// 调用方拥有四条带状数组；消元在其缓冲区上进行，节点数至少为 4。
Eigen::ArrayXd solve_tridiagonal(Eigen::ArrayXd lower, Eigen::ArrayXd diagonal,
                                Eigen::ArrayXd upper, Eigen::ArrayXd rhs);

}  // namespace cnn_compute::emd
