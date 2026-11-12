#include <emd/envelopes.hpp>

namespace cnn_compute::emd {
namespace detail {

std::optional<Envelopes> make_envelopes(const Array& signal, int width, Workspace& workspace,
                                     Interpolation method) {
    locate(signal, workspace);
    if (workspace.max_indices.size() < 2 || workspace.min_indices.size() < 2) return std::nullopt;
    auto maxima = refine(signal, workspace.max_indices, workspace);
    auto minima = refine(signal, workspace.min_indices, workspace);
    double left_axis = 0.0, right_axis = static_cast<double>(signal.size() - 1);
    if (signal[0] > maxima.values[0]) left_axis = maxima.locations[0];
    else if (signal[0] < minima.values[0]) left_axis = minima.locations[0];
    if (signal[signal.size() - 1] < maxima.values[maxima.values.size() - 1])
        right_axis = maxima.locations[maxima.locations.size() - 1];
    else if (signal[signal.size() - 1] > minima.values[minima.values.size() - 1])
        right_axis = minima.locations[minima.locations.size() - 1];
    const Array query = Array::LinSpaced(signal.size(), 0.0, static_cast<double>(signal.size() - 1));
    return Envelopes{interpolate(mirror(maxima, left_axis, right_axis, width), query, method),
                     interpolate(mirror(minima, left_axis, right_axis, width), query, method)};
}
} // namespace detail

std::optional<Envelopes> envelopes(std::span<const double> signal, int mirror_extrema,
                                 Interpolation interpolation) {
    detail::Workspace workspace;
    return detail::make_envelopes(core::Map(signal.data(), signal.size()), mirror_extrema, workspace, interpolation);
}

} // namespace cnn_compute::emd
