#include "api.hpp"
#include <Eigen/Core>
#include <Eigen/QR>
#include <algorithm>
#include <cmath>
#include <complex>
#include <numbers>
#include <numeric>
#include <stdexcept>

namespace cnn_compute::filtering {
namespace {
    void finite(std::span< const double > values) {
        for (double v : values)
            if (!std::isfinite(v)) throw std::invalid_argument("signal must be finite");
    }
    using Complex              = std::complex< double >;
    constexpr double        pi = std::numbers::pi;
    std::array< double, 3 > polynomial(const std::vector< Complex > &roots) {
        if (roots.empty( )) return { 1, 0, 0 };
        if (roots.size( ) == 1) return { 1, -roots[0].real( ), 0 };
        return { 1, -(roots[0] + roots[1]).real( ), (roots[0] * roots[1]).real( ) };
    }
    void filter_inplace(std::span< double > x, std::span< const Sos > sos) {
        double initial = x.front( );
        for (const auto &section : sos) {
            const double b0 = section[0] / section[3], b1 = section[1] / section[3], b2 = section[2] / section[3];
            const double a1 = section[4] / section[3], a2 = section[5] / section[3];
            const double gain = (b0 + b1 + b2) / (1 + a1 + a2);
            double       z1 = initial * (gain - b0), z2 = initial * (b2 - a2 * gain);
            for (auto &value : x) {
                const double in = value, out = b0 * in + z1;
                z1    = b1 * in - a1 * out + z2;
                z2    = b2 * in - a2 * out;
                value = out;
            }
            initial *= gain;
        }
    }
}    // namespace
std::vector< Sos > butterworth(int order, double low, double high, double fs) {
    if (order < 1 || !std::isfinite(fs) || fs <= 0 || !std::isfinite(low) || !std::isfinite(high)
        || low < 0 || high <= low || low >= fs / 2)
        throw std::invalid_argument("invalid Butterworth frequency or order");
    const bool lp = low <= 0, hp = high >= fs / 2;
    if (lp && hp) throw std::invalid_argument("Butterworth must have a finite passband edge");
    std::vector< Complex > prototype, poles, zeros;
    for (int m = -order + 1; m < order; m += 2) prototype.push_back(-std::exp(Complex(0, pi * m / (2.0 * order))));
    double gain = 1;
    if (lp) {
        const double w = 4 * std::tan(pi * high / fs);
        gain           = std::pow(w, order);
        for (auto p : prototype) poles.push_back(w * p);
    } else if (hp) {
        const double w = 4 * std::tan(pi * low / fs);
        for (auto p : prototype) poles.push_back(w / p);
        zeros.resize(order, Complex(0));
    } else {
        const double lo = 4 * std::tan(pi * low / fs), hi = 4 * std::tan(pi * high / fs), bw = hi - lo, wo = std::sqrt(lo * hi);
        gain = std::pow(bw, order);
        for (auto p : prototype) {
            auto h = p * bw / 2.0, d = std::sqrt(h * h - wo * wo);
            // 二次方程两根乘积为wo²；直接h-d会在宽带/近Nyquist时消去有效位。
            auto first = h + d, second = h - d;
            if (std::abs(first) < std::abs(second)) std::swap(first, second);
            poles.push_back(first);
            poles.push_back((wo * wo) / first);
        }
        zeros.resize(order, Complex(0));
    }
    Complex numerator(1), denominator(1);
    for (auto z : zeros) numerator *= 4.0 - z;
    for (auto p : poles) denominator *= 4.0 - p;
    gain *= std::real(numerator / denominator);
    for (auto &z : zeros) z = (4.0 + z) / (4.0 - z);
    for (auto &p : poles) p = (4.0 + p) / (4.0 - p);
    while (zeros.size( ) < poles.size( )) zeros.push_back(-1.0);

    std::vector< std::vector< Complex > > groups;
    while (!poles.empty( )) {
        // 先给最接近单位圆的高Q极点配最近零点，避免低Q段先用掉可消除高Q
        // 内部增益的零点。最终反转段顺序，先运行低Q段，与zpk2sos原则一致。
        auto it = std::min_element(poles.begin( ), poles.end( ), [](auto a, auto b) { return std::abs(1 - std::abs(a)) < std::abs(1 - std::abs(b)); });
        auto p  = *it;
        poles.erase(it);
        std::vector< Complex > pair{ p };
        if (std::abs(p.imag( )) > 1e-12) {
            auto other = std::min_element(poles.begin( ), poles.end( ), [p](auto a, auto b) { return std::abs(a - std::conj(p)) < std::abs(b - std::conj(p)); });
            pair.push_back(*other);
            poles.erase(other);
        } else {
            auto other = std::find_if(poles.begin( ), poles.end( ), [](auto v) { return std::abs(v.imag( )) <= 1e-12; });
            if (other != poles.end( )) {
                pair.push_back(*other);
                poles.erase(other);
            }
        }
        groups.push_back(std::move(pair));
    }
    std::vector< Sos > sections;
    for (const auto &pair : groups) {
        std::vector< Complex > zpair;
        for (auto p : pair) {
            auto it = std::min_element(zeros.begin( ), zeros.end( ), [p](auto a, auto b) { return std::abs(a - p) < std::abs(b - p); });
            zpair.push_back(*it);
            zeros.erase(it);
        }
        auto b = polynomial(zpair), a = polynomial(pair);
        sections.push_back({ b[0], b[1], b[2], a[0], a[1], a[2] });
    }
    std::reverse(sections.begin( ), sections.end( ));
    for (int i = 0; i < 3; ++i) sections.front( )[i] *= gain;
    return sections;
}
void Workspace::prepare(std::size_t n, std::size_t sections, int padlen) {
    const auto edge = padlen < 0 ? 3 * (2 * sections + 1) : static_cast< std::size_t >(padlen);
    padded.resize(n + 2 * edge);
}
namespace execution {
    void sosfiltfilt(std::span< const double > input, std::span< const Sos > sos, std::span< double > output, Workspace &w, int padlen) {
        int zeros_b = 0, zeros_a = 0;
        for (const auto &s : sos) {
            zeros_b += s[2] == 0;
            zeros_a += s[5] == 0;
        }
        const int edge = padlen < 0 ? 3 * (static_cast< int >(2 * sos.size( ) + 1) - std::min(zeros_a, zeros_b)) : padlen;
        if (input.empty( ) || input.size( ) <= static_cast< std::size_t >(edge) || sos.empty( ))
            throw std::invalid_argument("signal must be longer than SOS pad length");
        w.padded.resize(input.size( ) + 2 * edge);
        auto      &x = w.padded;
        const auto n = input.size( );
        std::copy(input.begin( ), input.end( ), x.begin( ) + edge);
        for (int i = 0; i < edge; ++i) {
            x[i]            = 2 * input.front( ) - input[edge - i];
            x[edge + n + i] = 2 * input.back( ) - input[n - 2 - i];
        }
        filter_inplace(x, sos);
        std::reverse(x.begin( ), x.end( ));
        filter_inplace(x, sos);
        for (std::size_t i = 0; i < n; ++i) output[i] = x[x.size( ) - 1 - edge - i];
    }
}    // namespace execution
std::vector< double > sosfiltfilt(std::span< const double > input, std::span< const Sos > sos, int padlen) {
    finite(input);
    if (padlen < -1) throw std::invalid_argument("padlen must be -1 or nonnegative");
    for (const auto &section : sos) {
        finite(section);
        if (section[3] != 1.0) throw std::invalid_argument("SOS a0 must be one");
    }
    Workspace             w;
    std::vector< double > out(input.size( ));
    execution::sosfiltfilt(input, sos, out, w, padlen);
    return out;
}
std::vector< double > hann(std::size_t n) {
    std::vector< double > w(n, 1);
    if (n > 1)
        for (std::size_t i = 0; i < n; ++i) w[i] = 0.5 - 0.5 * std::cos(2 * pi * i / n);
    return w;
}
std::vector< double > detrend(std::span< const double > x, bool linear) {
    finite(x);
    if (x.empty( )) throw std::invalid_argument("detrend requires nonempty input");
    Eigen::Map< const Eigen::ArrayXd > a(x.data( ), x.size( ));
    const double                       mean = a.mean( );
    std::vector< double >              out(x.size( ));
    Eigen::Map< Eigen::ArrayXd >(out.data( ), out.size( )) = a - mean;
    if (linear && x.size( ) > 1) {
        const double center     = (x.size( ) - 1) * 0.5;
        double       covariance = 0;
        for (std::size_t i = 0; i < x.size( ); ++i) covariance += (i - center) * (x[i] - mean);
        const double n = static_cast< double >(x.size( )), slope = covariance / (n * (n * n - 1) / 12);
        for (std::size_t i = 0; i < x.size( ); ++i) out[i] -= slope * (i - center);
    }
    return out;
}
std::vector< double > savgol(std::span< const double > x, int window, int order, int deriv, double delta) {
    finite(x);
    if (window < 1 || window % 2 != 1 || window > static_cast< int >(x.size( )) || order < 0 || order >= window || deriv < 0 || !std::isfinite(delta) || delta <= 0)
        throw std::invalid_argument("invalid Savitzky-Golay window or polynomial");
    std::vector< double > out(x.size( ), 0.0);
    if (deriv > order) return out;
    // 中心化坐标减少 Vandermonde 条件数；一次 QR 同时准备所有端点系数。
    const int       half = window / 2;
    Eigen::MatrixXd design(window, order + 1);
    for (int i = 0; i < window; ++i) {
        double p = 1, t = static_cast< double >(i - half) / std::max(1, half);
        for (int j = 0; j <= order; ++j) {
            design(i, j) = p;
            p *= t;
        }
    }
    Eigen::MatrixXd inverse = design.colPivHouseholderQr( ).solve(Eigen::MatrixXd::Identity(window, window));
    auto            weights = [&](int position) {
        Eigen::VectorXd evaluation = Eigen::VectorXd::Zero(order + 1);
        const double    t          = static_cast< double >(position - half) / std::max(1, half);
        for (int j = deriv; j <= order; ++j) {
            double factor = 1;
            for (int k = 0; k < deriv; ++k) factor *= j - k;
            evaluation[j] = factor * std::pow(t, j - deriv) / std::pow(std::max(1, half) * delta, deriv);
        }
        return Eigen::RowVectorXd(evaluation.transpose( ) * inverse);
    };
    const Eigen::RowVectorXd middle = weights(half);
    for (std::size_t i = half; i < x.size( ) - half; ++i)
        out[i] = middle.dot(Eigen::Map< const Eigen::VectorXd >(x.data( ) + i - half, window));
    for (int i = 0; i < half; ++i) {
        out[i]                    = weights(i).dot(Eigen::Map< const Eigen::VectorXd >(x.data( ), window));
        out[x.size( ) - half + i] = weights(window - half + i).dot(Eigen::Map< const Eigen::VectorXd >(x.data( ) + x.size( ) - window, window));
    }
    return out;
}
}    // namespace cnn_compute::filtering
