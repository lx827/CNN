#include <cnn_compute/emd.hpp>

// PCHIP 端点/斜率与逐项求值兼容 SciPy 1.18.1；BSD 归属见 ../LICENSE.scipy。

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace cnn_compute::emd {
namespace {
using Map = Eigen::Map<const Array>;
struct Extrema {
    Array locations;
    Array values;
};
struct Workspace {
    Array difference, left, center, right, denominator, shift, refined;
    Eigen::Array<bool, Eigen::Dynamic, 1> maxima, minima;
    std::vector<Eigen::Index> max_indices, min_indices;
};

void locate(const Array& signal, Workspace& workspace) {
    const auto n = signal.size();
    workspace.difference = signal.tail(n - 1) - signal.head(n - 1);
    workspace.maxima = (workspace.difference.head(n - 2) > 0.0)
        && (workspace.difference.tail(n - 2) <= 0.0);
    workspace.minima = (workspace.difference.head(n - 2) < 0.0)
        && (workspace.difference.tail(n - 2) >= 0.0);
    workspace.max_indices.clear();
    workspace.min_indices.clear();
    for (Eigen::Index i = 0; i < n - 2; ++i) {
        if (workspace.maxima[i]) workspace.max_indices.push_back(i + 1);
        if (workspace.minima[i]) workspace.min_indices.push_back(i + 1);
    }
}

Extrema refine(const Array& signal, const std::vector<Eigen::Index>& indices, Workspace& work) {
    const auto size = static_cast<Eigen::Index>(indices.size());
    work.left.resize(size);
    work.center.resize(size);
    work.right.resize(size);
    Extrema result{Array(size), Array(size)};
    for (Eigen::Index i = 0; i < size; ++i) {
        const auto index = indices[i];
        result.locations[i] = static_cast<double>(index);
        work.left[i] = signal[index - 1];
        work.center[i] = signal[index];
        work.right[i] = signal[index + 1];
    }
    work.denominator = work.left - 2.0 * work.center + work.right;
    work.shift = 0.5 * (work.left - work.right) / work.denominator;
    work.refined = work.center - ((work.right - work.left) / 2.0).square()
        / (4.0 * (work.denominator / 2.0));
    const auto accepted = ((work.denominator.abs() > std::numeric_limits<double>::epsilon())
        && (work.shift.abs() <= 0.5)).eval();
    result.locations += accepted.select(work.shift, 0.0);
    result.values = accepted.select(work.refined, work.center);
    return result;
}

Extrema mirror(const Extrema& extrema, double left_axis, double right_axis, int width) {
    std::vector<std::pair<double, double>> points;
    const auto n = extrema.locations.size();
    const auto count = std::min<Eigen::Index>(n, static_cast<Eigen::Index>(width) + 1);
    points.reserve(static_cast<std::size_t>(n + 2 * count));
    auto distinct = [](double a, double b) { return std::abs(a - b) > 1e-8 + 1e-5 * std::abs(b); };
    for (Eigen::Index i = 0; i < count; ++i) {
        const double location = 2.0 * left_axis - extrema.locations[i];
        if (location < extrema.locations[0] && distinct(location, extrema.locations[0]))
            points.emplace_back(location, extrema.values[i]);
    }
    for (Eigen::Index i = 0; i < n; ++i)
        points.emplace_back(extrema.locations[i], extrema.values[i]);
    for (Eigen::Index offset = 0; offset < count; ++offset) {
        const auto i = n - 1 - offset;
        const double location = 2.0 * right_axis - extrema.locations[i];
        if (location > extrema.locations[n - 1] && distinct(location, extrema.locations[n - 1]))
            points.emplace_back(location, extrema.values[i]);
    }
    std::stable_sort(points.begin(), points.end(), [](auto a, auto b) { return a.first < b.first; });
    points.erase(std::unique(points.begin(), points.end(), [](auto a, auto b) {
        return a.first == b.first;
    }), points.end());
    Extrema result{Array(points.size()), Array(points.size())};
    for (std::size_t i = 0; i < points.size(); ++i) {
        result.locations[i] = points[i].first;
        result.values[i] = points[i].second;
    }
    return result;
}

double endpoint(double h0, double h1, double m0, double m1) {
    double d = ((2.0 * h0 + h1) * m0 - h0 * m1) / (h0 + h1);
    auto sign = [](double v) { return (v > 0.0) - (v < 0.0); };
    if (sign(d) != sign(m0)) return 0.0;
    if (sign(m0) != sign(m1) && std::abs(d) > 3.0 * std::abs(m0)) return 3.0 * m0;
    return d;
}

Array evaluate_pchip(const Extrema& points, const Array& query) {
    const auto& x = points.locations;
    const auto& y = points.values;
    const auto n = x.size();
    const Array h = x.tail(n - 1) - x.head(n - 1);
    const Array slope = (y.tail(n - 1) - y.head(n - 1)) / h;
    Array derivative(n);
    if (n == 2) {
        derivative.setConstant(slope[0]);
    } else {
        derivative[0] = endpoint(h[0], h[1], slope[0], slope[1]);
        derivative[n - 1] = endpoint(h[n - 2], h[n - 3], slope[n - 2], slope[n - 3]);
        // SciPy 兼容的加权调和均值次序，批量计算由 Eigen 提供 SIMD。
        const Array before = slope.head(n - 2), after = slope.tail(n - 2);
        const Array w1 = 2.0 * h.tail(n - 2) + h.head(n - 2);
        const Array w2 = h.tail(n - 2) + 2.0 * h.head(n - 2);
        const Array harmonic = (w1 / before + w2 / after) / (w1 + w2);
        const auto same_sign = ((before > 0.0) == (after > 0.0))
            && (before != 0.0) && (after != 0.0);
        derivative.segment(1, n - 2) = same_sign.select(harmonic.inverse(), 0.0);
    }
    // 分段系数与 SciPy CubicHermiteSpline 相同；查询重排不改变输出顺序。
    const Array t = (derivative.head(n - 1) + derivative.tail(n - 1) - 2.0 * slope) / h;
    const Array c0 = t / h;
    const Array c1 = (slope - derivative.head(n - 1)) / h - t;
    const auto size = query.size();
    Array dx(size), a(size), b(size), c(size), d(size);
    for (Eigen::Index i = 0; i < size; ++i) {
        const auto found = std::upper_bound(x.data(), x.data() + n, query[i]) - x.data() - 1;
        const auto j = std::clamp<Eigen::Index>(found, 0, n - 2);
        dx[i] = query[i] - x[j];
        a[i] = c0[j]; b[i] = c1[j]; c[i] = derivative[j]; d[i] = y[j];
    }
    // SciPy PPoly 按常数到三次项累加。保留该次序，同时各项使用 Eigen SIMD。
    Array result = d;
    result += c * dx;
    Array power = dx * dx;
    result += b * power;
    power *= dx;
    result += a * power;
    if (!result.isFinite().all()) throw std::runtime_error("EMD 包络插值产生非有限值");
    return result;
}

std::optional<Envelopes> make_envelopes(const Array& signal, int width, Workspace& workspace) {
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
    return Envelopes{evaluate_pchip(mirror(maxima, left_axis, right_axis, width), query),
                     evaluate_pchip(mirror(minima, left_axis, right_axis, width), query)};
}
} // namespace

Array pchip(std::span<const double> x, std::span<const double> y, std::span<const double> query) {
    return evaluate_pchip({Map(x.data(), x.size()), Map(y.data(), y.size())}, Map(query.data(), query.size()));
}

std::optional<Envelopes> envelopes(std::span<const double> signal, int mirror_extrema) {
    Workspace workspace;
    return make_envelopes(Map(signal.data(), signal.size()), mirror_extrema, workspace);
}

std::optional<SiftResult> sift(std::span<const double> signal, const SiftParameters& parameters) {
    Array current = Map(signal.data(), signal.size());
    Array updated(current.size());
    Workspace workspace;
    for (int iteration = 1; iteration <= parameters.max_sifts; ++iteration) {
        const auto envelope = make_envelopes(current, parameters.mirror_extrema, workspace);
        if (!envelope) {
            if (iteration == 1) return std::nullopt;
            return SiftResult{std::move(current), iteration - 1, true};
        }
        updated = current - (envelope->upper + envelope->lower) / 2.0;
        const double denominator = current.square().sum();
        const double numerator = (updated - current).square().sum();
        current.swap(updated);
        if (denominator <= std::numeric_limits<double>::min()
            || numerator / denominator < parameters.sd_threshold)
            return SiftResult{std::move(current), iteration, true};
    }
    return SiftResult{std::move(current), parameters.max_sifts, false};
}
} // namespace cnn_compute::emd
