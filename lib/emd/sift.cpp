#include <emd/envelopes.hpp>
#include <emd/sifting.hpp>

#include <limits>

namespace cnn_compute::emd {
using core::Map;

std::optional< SiftInfo > execution::sift(std::span< const double > signal, std::span< double > out,
                                          const SiftParameters &parameters, SiftWorkspace &workspace) {
    auto &current = workspace.current;
    auto &updated = workspace.updated;
    current       = Map(signal.data( ), signal.size( ));
    updated.resize(current.size( ));
    int  count     = 0;
    bool converged = false;
    for (int iteration = 1; iteration <= parameters.max_sifts; ++iteration) {
        const auto envelope = detail::make_envelopes(current, parameters.mirror_extrema,
                                                     workspace.envelope, parameters.interpolation);
        if (!envelope) {
            if (iteration == 1) return std::nullopt;
            converged = true;
            break;
        }
        updated                  = current - (Map(envelope->upper.data( ), envelope->upper.size( )) + Map(envelope->lower.data( ), envelope->lower.size( ))) / 2.0;
        const double denominator = current.square( ).sum( );
        const double numerator   = (updated - current).square( ).sum( );
        current.swap(updated);
        count     = iteration;
        converged = denominator <= std::numeric_limits< double >::min( )
                    || (parameters.stopping_rule == StoppingRule::sd
                            ? numerator / denominator < parameters.sd_threshold
                            : rilling_stop(envelope->upper, envelope->lower, parameters.rilling_thresholds));
        if (converged) break;
    }
    Eigen::Map< Array >(out.data( ), out.size( )) = current;
    return SiftInfo{ count, converged };
}

std::optional< SiftResult > sift(std::span< const double > signal, const SiftParameters &parameters) {
    SiftWorkspace workspace;
    Array         output(signal.size( ));
    const auto    info = execution::sift(signal, { output.data( ), signal.size( ) }, parameters, workspace);
    if (!info) return std::nullopt;
    return SiftResult{ std::move(output), info->iterations, info->converged };
}
}    // namespace cnn_compute::emd
