#include <emd/envelopes.hpp>

#include <interpolation/execution.hpp>
#include <algorithm>
#include <stdexcept>

namespace cnn_compute::emd {
namespace detail {

    interpolation::Method select(Interpolation method) {
        return method == Interpolation::pchip ? interpolation::Method::pchip
                                              : interpolation::Method::cubic;
    }

    std::optional< EnvelopeSpans > make_envelopes(const Array &signal, int width, Workspace &workspace,
                                                  Interpolation method) {
        locate(signal, workspace);
        if (workspace.max_indices.size( ) < 2 || workspace.min_indices.size( ) < 2) return std::nullopt;
        // 两侧节点数不同：一次按最大值备容，两次 refine 之间不再扩容。
        workspace.reserve(std::max(workspace.max_indices.size( ), workspace.min_indices.size( )));
        refine(signal, workspace.max_indices, workspace, workspace.max_locations, workspace.max_values);
        refine(signal, workspace.min_indices, workspace, workspace.min_locations, workspace.min_values);
        double left_axis = 0.0, right_axis = static_cast< double >(signal.size( ) - 1);
        if (signal[0] > workspace.max_values[0])
            left_axis = workspace.max_locations[0];
        else if (signal[0] < workspace.min_values[0])
            left_axis = workspace.min_locations[0];
        const auto last = signal.size( ) - 1;
        if (signal[last] < workspace.max_values[workspace.max_indices.size( ) - 1])
            right_axis = workspace.max_locations[workspace.max_indices.size( ) - 1];
        else if (signal[last] > workspace.min_values[workspace.min_indices.size( ) - 1])
            right_axis = workspace.min_locations[workspace.min_indices.size( ) - 1];
        const auto count = static_cast< std::size_t >(signal.size( ));
        if (workspace.query.size( ) != signal.size( ))
            workspace.query = Array::LinSpaced(signal.size( ), 0.0, static_cast< double >(last));
        if (workspace.upper.size( ) < static_cast< Eigen::Index >(count)) {
            workspace.upper.resize(static_cast< Eigen::Index >(count));
            workspace.lower.resize(static_cast< Eigen::Index >(count));
        }
        const auto        mode  = select(method);
        auto *const       upper = workspace.upper.data( );
        auto *const       lower = workspace.lower.data( );
        const auto *const query = workspace.query.data( );
        const auto        nodes = mirror({ workspace.max_locations.data( ), workspace.max_indices.size( ) },
                                         { workspace.max_values.data( ), workspace.max_indices.size( ) },
                                         left_axis, right_axis, width, workspace);
        interpolation::execution::interpolate({ workspace.mirror_locations.data( ), nodes },
                                              { workspace.mirror_values.data( ), nodes },
                                              { query, count }, { upper, count }, mode,
                                              workspace.interpolation);
        if (!workspace.upper.head(signal.size( )).isFinite( ).all( ))
            throw std::runtime_error("插值产生非有限值");
        const auto lower_nodes = mirror({ workspace.min_locations.data( ), workspace.min_indices.size( ) },
                                        { workspace.min_values.data( ), workspace.min_indices.size( ) },
                                        left_axis, right_axis, width, workspace);
        interpolation::execution::interpolate({ workspace.mirror_locations.data( ), lower_nodes },
                                              { workspace.mirror_values.data( ), lower_nodes },
                                              { query, count }, { lower, count }, mode,
                                              workspace.interpolation);
        if (!workspace.lower.head(signal.size( )).isFinite( ).all( ))
            throw std::runtime_error("插值产生非有限值");
        return EnvelopeSpans{ { upper, count }, { lower, count } };
    }
}    // namespace detail

std::optional< Envelopes > envelopes(std::span< const double > signal, int mirror_extrema,
                                     Interpolation interpolation) {
    detail::Workspace workspace;
    const auto        envelope = detail::make_envelopes(core::Map(signal.data( ), signal.size( )),
                                                        mirror_extrema, workspace, interpolation);
    if (!envelope) return std::nullopt;
    // 公开结果独立拥有存储，从工作区缓冲复制一次。
    return Envelopes{ core::Map(envelope->upper.data( ), envelope->upper.size( )),
                      core::Map(envelope->lower.data( ), envelope->lower.size( )) };
}

}    // namespace cnn_compute::emd
