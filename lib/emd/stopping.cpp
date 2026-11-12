#include <emd/emd.hpp>
#include <limits>

namespace cnn_compute::emd {
using core::Map;

bool rilling_stop(std::span< const double > upper, std::span< const double > lower,
                  const std::array< double, 3 > &thresholds) {
    const Map   high(upper.data( ), upper.size( )), low(lower.data( ), lower.size( ));
    const Array mean      = ((high + low) / 2.0).abs( );
    const Array amplitude = (high - low).abs( ) / 2.0;
    Array       ratio     = (amplitude > 0.0).select(mean / amplitude, std::numeric_limits< double >::infinity( ));
    ratio                 = ((mean == 0.0) && (amplitude == 0.0)).select(0.0, ratio);
    return static_cast< double >((ratio > thresholds[0]).count( )) / ratio.size( ) <= thresholds[2]
           && (ratio <= thresholds[1]).all( );
}

}    // namespace cnn_compute::emd
