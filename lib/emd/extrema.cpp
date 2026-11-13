#include <emd/extrema.hpp>

#include <algorithm>
#include <cmath>
#include <limits>

namespace cnn_compute::emd::detail {

void locate(const Array &signal, Workspace &workspace) {
    const auto n         = signal.size( );
    workspace.difference = signal.tail(n - 1) - signal.head(n - 1);
    workspace.maxima     = (workspace.difference.head(n - 2) > 0.0)
                           && (workspace.difference.tail(n - 2) <= 0.0);
    workspace.minima     = (workspace.difference.head(n - 2) < 0.0)
                           && (workspace.difference.tail(n - 2) >= 0.0);
    workspace.max_indices.clear( );
    workspace.min_indices.clear( );
    for (Eigen::Index i = 0; i < n - 2; ++i) {
        if (workspace.maxima[i]) workspace.max_indices.push_back(i + 1);
        if (workspace.minima[i]) workspace.min_indices.push_back(i + 1);
    }
}

void Workspace::reserve(std::size_t nodes) {
    const auto size = static_cast< Eigen::Index >(nodes);
    if (max_locations.size( ) < size)
        for (auto *item : { &left, &center, &right, &denominator, &shift, &refined,
                            &max_locations, &max_values, &min_locations, &min_values })
            item->resize(size);
    if (accepted.size( ) < size) accepted.resize(size);
}

void refine(const Array &signal, const std::vector< Eigen::Index > &indices, Workspace &work,
            Array &locations, Array &values) {
    const auto size   = static_cast< Eigen::Index >(indices.size( ));
    auto       left   = work.left.head(size);
    auto       center = work.center.head(size);
    auto       right  = work.right.head(size);
    for (Eigen::Index i = 0; i < size; ++i) {
        const auto index = indices[i];
        locations[i]     = static_cast< double >(index);
        left[i]          = signal[index - 1];
        center[i]        = signal[index];
        right[i]         = signal[index + 1];
    }
    auto denominator        = work.denominator.head(size);
    denominator             = left - 2.0 * center + right;
    auto shift              = work.shift.head(size);
    shift                   = 0.5 * (left - right) / denominator;
    work.refined.head(size) = center - ((right - left) / 2.0).square( ) / (4.0 * (denominator / 2.0));
    auto flags              = work.accepted.head(size);
    flags                   = (denominator.abs( ) > std::numeric_limits< double >::epsilon( ))
                              && (shift.abs( ) <= 0.5);
    locations.head(size) += flags.select(shift, 0.0);
    values.head(size) = flags.select(work.refined.head(size), center);
}

std::size_t mirror(std::span< const double > locations, std::span< const double > values,
                   double left_axis, double right_axis, int width, Workspace &work) {
    auto      &points = work.mirror_points;
    const auto n      = static_cast< Eigen::Index >(locations.size( ));
    const auto count  = std::min< Eigen::Index >(n, static_cast< Eigen::Index >(width) + 1);
    points.clear( );
    points.reserve(static_cast< std::size_t >(n + 2 * count));
    auto distinct = [](double a, double b) { return std::abs(a - b) > 1e-8 + 1e-5 * std::abs(b); };
    for (Eigen::Index i = 0; i < count; ++i) {
        const double location = 2.0 * left_axis - locations[i];
        if (location < locations[0] && distinct(location, locations[0]))
            points.emplace_back(location, values[i]);
    }
    for (Eigen::Index i = 0; i < n; ++i) points.emplace_back(locations[i], values[i]);
    for (Eigen::Index offset = 0; offset < count; ++offset) {
        const auto   i        = n - 1 - offset;
        const double location = 2.0 * right_axis - locations[i];
        if (location > locations[n - 1] && distinct(location, locations[n - 1]))
            points.emplace_back(location, values[i]);
    }
    std::stable_sort(points.begin( ), points.end( ), [](auto a, auto b) { return a.first < b.first; });
    points.erase(std::unique(points.begin( ), points.end( ), [](auto a, auto b) {
                     return a.first == b.first;
                 }),
                 points.end( ));
    const auto total = points.size( );
    if (static_cast< std::size_t >(work.mirror_locations.size( )) < total) {
        work.mirror_locations.resize(static_cast< Eigen::Index >(total));
        work.mirror_values.resize(static_cast< Eigen::Index >(total));
    }
    for (std::size_t i = 0; i < total; ++i) {
        work.mirror_locations[i] = points[i].first;
        work.mirror_values[i]    = points[i].second;
    }
    return total;
}

}    // namespace cnn_compute::emd::detail
