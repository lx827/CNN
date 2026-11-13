#pragma once

#include <core/interpolation.hpp>
#include <interpolation/execution.hpp>
#include <span>
#include <vector>

namespace cnn_compute::emd::detail {

using core::Array;

// 一次筛分持有的工作区：极值检测/精化、镜像延拓、包络输出与插值子工作区
// 跨迭代复用，容量只增不减；同规模迭代除首次准备外不再分配。
struct Workspace {
    Array                                   difference, left, center, right, denominator, shift, refined;
    Eigen::Array< bool, Eigen::Dynamic, 1 > maxima, minima, accepted;
    std::vector< Eigen::Index >             max_indices, min_indices;
    Array                                   max_locations, max_values, min_locations, min_values;
    Array                                   mirror_locations, mirror_values;
    Array                                   query, upper, lower;
    interpolation::Workspace                interpolation;

    // 为一次包络计算准备全部节点级缓冲：参数取上下两侧极值数的最大值，
    // 在两次 refine 之前调用一次。refine 不再自行扩容——中途 resize 会
    // 重新分配并丢弃已写入的另一侧节点。
    void reserve(std::size_t nodes);
};

void locate(const Array &signal, Workspace &workspace);

// 抛物线精化结果写入 locations/values；容量已由调用方 reserve 建立，
// head(indices.size()) 生效。
void refine(const Array &signal, const std::vector< Eigen::Index > &indices, Workspace &work,
            Array &locations, Array &values);

// locations 严格递增；按左镜像、原节点、右镜像有序直写 work.mirror_locations/values。
// 返回有效节点数；数组仅在节点容量增长时分配，借用在下次 mirror 前有效。
std::size_t mirror(std::span< const double > locations, std::span< const double > values,
                   double left_axis, double right_axis, int width, Workspace &work);

}    // namespace cnn_compute::emd::detail
