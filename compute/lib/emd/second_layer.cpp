// emd 0.8.1 二层分解成功域的 C++ 组合；归属见 lib/LICENSE.emd。
#include <emd/second_layer.hpp>
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace cnn_compute::emd {
namespace {
    void validate_columns(const std::vector< std::span< const double > > &columns) {
        if (columns.empty( ) || columns[0].size( ) < 3)
            throw std::invalid_argument("二层输入至少一列且每列至少三个点");
        const auto size = columns[0].size( );
        for (const auto column : columns) {
            if (column.size( ) != size) throw std::invalid_argument("二层输入各列长度不同");
            for (double value : column)
                if (!std::isfinite(value)) throw std::invalid_argument("二层输入必须有限");
        }
    }
}    // namespace
namespace execution {
    SecondLayerResult sift_second_layer(const std::vector< std::span< const double > > &first_layer,
                                        const Options &options, Workspace &workspace) {
        SecondLayerResult result;
        result.layers.reserve(first_layer.size( ));
        for (const auto column : first_layer) {
            auto layer          = execution::sift(column, options, workspace);
            result.output_depth = std::max(result.output_depth, layer.components.size( ));
            result.layers.push_back(std::move(layer));
        }
        return result;
    }
    SecondLayerResult mask_sift_second_layer(const std::vector< std::span< const double > > &first_layer,
                                             std::span< const double >                       frequencies,
                                             const MaskOptions &options, MaskWorkspace &workspace) {
        SecondLayerResult result;
        result.layers.reserve(first_layer.size( ));
        auto current = options;
        for (std::size_t i = 0; i < first_layer.size( ); ++i) {
            current.mask_freqs.assign(frequencies.begin( ) + i, frequencies.end( ));
            auto layer          = execution::mask_sift(first_layer[i], current, workspace);
            result.output_depth = std::max(result.output_depth, layer.decomposition.components.size( ));
            result.layers.push_back(std::move(layer.decomposition));
        }
        return result;
    }
}    // namespace execution
SecondLayerResult sift_second_layer(const std::vector< std::span< const double > > &first_layer,
                                    const Options                                  &options) {
    validate_columns(first_layer);
    validate(options);
    Workspace workspace;
    workspace.prepare(first_layer[0].size( ), options.envelope.pad_width);
    return execution::sift_second_layer(first_layer, options, workspace);
}
SecondLayerResult mask_sift_second_layer(const std::vector< std::span< const double > > &first_layer,
                                         std::span< const double >                       frequencies,
                                         const MaskOptions                              &options) {
    validate_columns(first_layer);
    validate(options);
    if (frequencies.size( ) < first_layer.size( ))
        throw std::invalid_argument("二层 mask 数必须至少等于输入列数");
    for (double frequency : frequencies)
        if (!std::isfinite(frequency)) throw std::invalid_argument("mask 频率必须有限");
    MaskWorkspace workspace;
    workspace.prepare(first_layer[0].size( ), options.envelope.pad_width);
    return execution::mask_sift_second_layer(first_layer, frequencies, options, workspace);
}
}    // namespace cnn_compute::emd
