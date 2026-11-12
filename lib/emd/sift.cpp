#include <emd/envelopes.hpp>

#include <limits>
#include <utility>

namespace cnn_compute::emd {
using core::Map;

std::optional< SiftResult > sift(std::span< const double > signal, const SiftParameters &parameters) {
    Array             current = Map(signal.data( ), signal.size( ));
    Array             updated(current.size( ));
    detail::Workspace workspace;
    for (int iteration = 1; iteration <= parameters.max_sifts; ++iteration) {
        const auto envelope = detail::make_envelopes(current, parameters.mirror_extrema, workspace,
                                                     parameters.interpolation);
        if (!envelope) {
            if (iteration == 1) return std::nullopt;
            return SiftResult{ std::move(current), iteration - 1, true };
        }
        updated                  = current - (envelope->upper + envelope->lower) / 2.0;
        const double denominator = current.square( ).sum( );
        const double numerator   = (updated - current).square( ).sum( );
        current.swap(updated);
        const bool stop = parameters.stopping_rule == StoppingRule::sd
                              ? numerator / denominator < parameters.sd_threshold
                              : rilling_stop({ envelope->upper.data( ), static_cast< std::size_t >(envelope->upper.size( )) },
                                             { envelope->lower.data( ), static_cast< std::size_t >(envelope->lower.size( )) },
                                             parameters.rilling_thresholds);
        if (denominator <= std::numeric_limits< double >::min( ) || stop)
            return SiftResult{ std::move(current), iteration, true };
    }
    return SiftResult{ std::move(current), parameters.max_sifts, false };
}
}    // namespace cnn_compute::emd
