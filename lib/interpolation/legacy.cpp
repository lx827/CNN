#include <core/interpolation.hpp>
#include <core/tridiagonal.hpp>

// PCHIP/cubic 导数、系数与逐项求值兼容 SciPy 1.18.1；BSD 见 ../LICENSE.scipy。
#include <Eigen/LU>
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace cnn_compute::core {
namespace {
double endpoint(double h0, double h1, double m0, double m1) {
    double d = ((2.0 * h0 + h1) * m0 - h0 * m1) / (h0 + h1);
    auto sign = [](double v) { return (v > 0.0) - (v < 0.0); };
    if (sign(d) != sign(m0)) return 0.0;
    if (sign(m0) != sign(m1) && std::abs(d) > 3.0 * std::abs(m0)) return 3.0 * m0;
    return d;
}

Array evaluate_hermite(const Knots& points, const Array& query, const Array& derivative) {
    const auto& x = points.locations;
    const auto& y = points.values;
    const auto n = x.size();
    const Array h = x.tail(n - 1) - x.head(n - 1);
    const Array slope = (y.tail(n - 1) - y.head(n - 1)) / h;
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
    if (!result.isFinite().all()) throw std::runtime_error("插值产生非有限值");
    return result;
}

Array pchip_derivatives(const Knots& points) {
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
    return derivative;
}

Array cubic_derivatives(const Knots& points) {
    const auto& x = points.locations;
    const auto& y = points.values;
    const auto n = x.size();
    const Array h = x.tail(n - 1) - x.head(n - 1);
    const Array slope = (y.tail(n - 1) - y.head(n - 1)) / h;
    if (n == 2) return Array::Constant(2, slope[0]);
    if (n == 3) {
        Eigen::Matrix3d matrix;
        matrix << 1.0, 1.0, 0.0, h[1], 2.0 * (h[0] + h[1]), h[0], 0.0, 1.0, 1.0;
        Eigen::Vector3d rhs(2.0 * slope[0],
            3.0 * (h[0] * slope[1] + h[1] * slope[0]), 2.0 * slope[1]);
        return matrix.partialPivLu().solve(rhs).array();
    }
    Array diagonal(n), upper(n - 1), lower(n - 1), rhs(n);
    diagonal.segment(1, n - 2) = 2.0 * (h.head(n - 2) + h.tail(n - 2));
    upper.tail(n - 2) = h.head(n - 2);
    lower.head(n - 2) = h.tail(n - 2);
    rhs.segment(1, n - 2) = 3.0 * (h.tail(n - 2) * slope.head(n - 2)
        + h.head(n - 2) * slope.tail(n - 2));
    diagonal[0] = h[1];
    upper[0] = x[2] - x[0];
    double length = x[2] - x[0];
    rhs[0] = ((h[0] + 2.0 * length) * h[1] * slope[0]
        + h[0] * h[0] * slope[1]) / length;
    diagonal[n - 1] = h[n - 3];
    lower[n - 2] = x[n - 1] - x[n - 3];
    length = x[n - 1] - x[n - 3];
    rhs[n - 1] = (h[n - 2] * h[n - 2] * slope[n - 3]
        + (2.0 * length + h[n - 2]) * h[n - 3] * slope[n - 2]) / length;
    return solve_tridiagonal(std::move(lower), std::move(diagonal), std::move(upper), std::move(rhs));
}

} // namespace

Array interpolate(const Knots& points, const Array& query, Interpolation method) {
    const Array derivative = method == Interpolation::pchip
        ? pchip_derivatives(points) : cubic_derivatives(points);
    return evaluate_hermite(points, query, derivative);
}

Array pchip(std::span<const double> x, std::span<const double> y, std::span<const double> query) {
    return interpolate({Map(x.data(), x.size()), Map(y.data(), y.size())}, Map(query.data(), query.size()),
                       Interpolation::pchip);
}

Array cubic(std::span<const double> x, std::span<const double> y, std::span<const double> query) {
    return interpolate({Map(x.data(), x.size()), Map(y.data(), y.size())}, Map(query.data(), query.size()),
                       Interpolation::cubic);
}

} // namespace cnn_compute::core
