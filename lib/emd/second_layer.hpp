#pragma once

#include <emd/mask.hpp>

namespace cnn_compute::emd {

struct SecondLayerResult {
    // first-layer 顺序；每个结果独立拥有 second-layer 各列。绑定负责零填充布局。
    std::vector< Result > layers;
    std::size_t           output_depth = 0;
};

// first_layer 是等长输入列；对全部列分别调用 sift，max_imfs 控制每列分解。
// output_depth 为实际最大结果列数，包含基础 sift 返回的真实残差。
SecondLayerResult sift_second_layer(const std::vector< std::span< const double > > &first_layer,
                                    const Options                                  &options);
// 每个 first-layer 列使用 frequencies[index:]；深度取实际最大结果列数。
SecondLayerResult mask_sift_second_layer(const std::vector< std::span< const double > > &first_layer,
                                         std::span< const double >                       frequencies,
                                         const MaskOptions                              &options);
namespace execution {
    SecondLayerResult sift_second_layer(const std::vector< std::span< const double > > &first_layer,
                                        const Options &options, Workspace &workspace);
    SecondLayerResult mask_sift_second_layer(const std::vector< std::span< const double > > &first_layer,
                                             std::span< const double >                       frequencies,
                                             const MaskOptions &options, MaskWorkspace &workspace);
}    // namespace execution
}    // namespace cnn_compute::emd
