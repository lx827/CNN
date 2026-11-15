#pragma once

#include <Eigen/Core>

namespace cnn_compute::core {

using Array = Eigen::ArrayXd;
using Map   = Eigen::Map< const Array >;

}    // namespace cnn_compute::core
