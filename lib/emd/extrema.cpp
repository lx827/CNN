#include <emd/extrema.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

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

Extrema refine(const Array &signal, const std::vector< Eigen::Index > &indices, Workspace &work) {
    const auto size = static_cast< Eigen::Index >(indices.size( ));
    work.left.resize(size);
    work.center.resize(size);
    work.right.resize(size);
    Extrema result{ Array(size), Array(size) };
    for (Eigen::Index i = 0; i < size; ++i) {
        const auto index    = indices[i];
        result.locations[i] = static_cast< double >(index);
        work.left[i]        = signal[index - 1];
        work.center[i]      = signal[index];
        work.right[i]       = signal[index + 1];
    }
    work.denominator    = work.left - 2.0 * work.center + work.right;
    work.shift          = 0.5 * (work.left - work.right) / work.denominator;
    work.refined        = work.center - ((work.right - work.left) / 2.0).square( ) / (4.0 * (work.denominator / 2.0));
    const auto accepted = ((work.denominator.abs( ) > std::numeric_limits< double >::epsilon( ))
                           && (work.shift.abs( ) <= 0.5))
                              .eval( );
    result.locations += accepted.select(work.shift, 0.0);
    result.values = accepted.select(work.refined, work.center);
    return result;
}

Extrema mirror(const Extrema &extrema, double left_axis, double right_axis, int width) {
    std::vector< std::pair< double, double > > points;
    const auto                                 n     = extrema.locations.size( );
    const auto                                 count = std::min< Eigen::Index >(n, static_cast< Eigen::Index >(width) + 1);
    points.reserve(static_cast< std::size_t >(n + 2 * count));
    auto distinct = [](double a, double b) { return std::abs(a - b) > 1e-8 + 1e-5 * std::abs(b); };
    for (Eigen::Index i = 0; i < count; ++i) {
        const double location = 2.0 * left_axis - extrema.locations[i];
        if (location < extrema.locations[0] && distinct(location, extrema.locations[0]))
            points.emplace_back(location, extrema.values[i]);
    }
    for (Eigen::Index i = 0; i < n; ++i)
        points.emplace_back(extrema.locations[i], extrema.values[i]);
    for (Eigen::Index offset = 0; offset < count; ++offset) {
        const auto   i        = n - 1 - offset;
        const double location = 2.0 * right_axis - extrema.locations[i];
        if (location > extrema.locations[n - 1] && distinct(location, extrema.locations[n - 1]))
            points.emplace_back(location, extrema.values[i]);
    }
    std::stable_sort(points.begin( ), points.end( ), [](auto a, auto b) { return a.first < b.first; });
    points.erase(std::unique(points.begin( ), points.end( ), [](auto a, auto b) {
                     return a.first == b.first;
                 }),
                 points.end( ));
    Extrema result{ Array(points.size( )), Array(points.size( )) };
    for (std::size_t i = 0; i < points.size( ); ++i) {
        result.locations[i] = points[i].first;
        result.values[i]    = points[i].second;
    }
    return result;
}

}    // namespace cnn_compute::emd::detail
