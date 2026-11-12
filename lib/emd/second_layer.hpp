#pragma once

#include <emd/mask.hpp>

namespace cnn_compute::emd {

struct SecondLayerResult {
    // first-layer 顺序；每个结果独立拥有 second-layer 各列。绑定负责零填充布局。
    std::vector<Result> layers;
    std::size_t output_depth = 0;
};

// first_layer 是等长输入列；max_imfs 必须明确且不超过 first_layer.size()。
// 保留 emd 0.8.1 的成功域：该入口仅处理前 max_imfs 个 first-layer 列。
SecondLayerResult sift_second_layer(const std::vector<std::span<const double>>& first_layer,
                                    const Options& options);
// 每个 first-layer 列使用 frequencies[index:]；输出深度为 options.max_imfs。
SecondLayerResult mask_sift_second_layer(const std::vector<std::span<const double>>& first_layer,
                                         std::span<const double> frequencies,
                                         const MaskOptions& options);
namespace execution {
SecondLayerResult sift_second_layer(const std::vector<std::span<const double>>& first_layer,
                                    const Options& options, Workspace& workspace);
SecondLayerResult mask_sift_second_layer(const std::vector<std::span<const double>>& first_layer,
                                         std::span<const double> frequencies,
                                         const MaskOptions& options, MaskWorkspace& workspace);
}
} // namespace cnn_compute::emd
