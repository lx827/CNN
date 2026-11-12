#pragma once

#include <core/array.hpp>
#include <span>

namespace cnn_compute::interpolation {

enum class Method { splrep,
                    pchip,
                    cubic };

// 节点有限且严格递增，x/y 等长；splrep 至少四节点，其余至少两节点。
// 输出独立拥有存储；查询允许外推，按原查询顺序返回。
core::Array interpolate(std::span< const double > x, std::span< const double > y,
                        std::span< const double > query, Method method);

}    // namespace cnn_compute::interpolation
