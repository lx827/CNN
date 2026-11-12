#include "api.hpp"
#include "execution.hpp"
#include <filtering/api.hpp>
#include <transforms/hilbert.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>

namespace cnn_compute::numeric {
namespace {
    using core::Array;
    void check(std::span< const double > x, std::size_t minimum = 1) {
        if (x.size( ) < minimum) throw std::invalid_argument("signal is too short");
        for (auto v : x)
            if (!std::isfinite(v)) throw std::invalid_argument("signal must be finite");
    }
    void rate(double fs) {
        if (!std::isfinite(fs) || fs <= 0) throw std::invalid_argument("sample rate must be positive");
    }
    Statistics stats(std::span< const double > x, double floor) {
        const Eigen::Map< const Array > a(x.data( ), x.size( ));
        const auto                      abs  = a.abs( );
        const double                    peak = abs.maxCoeff( ), rms = std::sqrt(a.square( ).mean( ));
        const double                    mean_abs = abs.mean( ), mean_sqrt = (abs + floor).sqrt( ).mean( );
        const double                    mean = a.mean( ), variance = (a - mean).square( ).mean( );
        const double                    threshold = std::numeric_limits< double >::epsilon( ) * std::abs(mean);
        double                          kurt = std::numeric_limits< double >::quiet_NaN( ), skew = kurt;
        if (variance > threshold * threshold) {
            kurt = (a - mean).pow(4).mean( ) / (variance * variance);
            skew = (a - mean).cube( ).mean( ) / std::pow(variance, 1.5);
        }
        return { peak, rms, kurt, skew, mean_sqrt > 1e-12 ? peak / (mean_sqrt * mean_sqrt) : 0,
                 mean_abs > 1e-12 ? rms / mean_abs : 0, mean_abs > 1e-12 ? peak / mean_abs : 0, rms > 1e-12 ? peak / rms : 0 };
    }
}    // namespace
namespace execution {
    void amplitude_spectrum(std::span< const double > x, std::span< double > amplitude,
                            std::span< const double > window, std::span< double > buffer,
                            std::span< fourier::Complex > transformed, fourier::Plan &plan, bool remove_mean) {
        const auto   n                               = x.size( );
        const double gain                            = Eigen::Map< const core::Array >(window.data( ), n).sum( );
        const double mean                            = remove_mean ? Eigen::Map< const core::Array >(x.data( ), n).mean( ) : 0.;
        Eigen::Map< core::Array >(buffer.data( ), n) = (Eigen::Map< const core::Array >(x.data( ), n) - mean) * Eigen::Map< const core::Array >(window.data( ), n);
        plan.forward(buffer, transformed);
        for (std::size_t k = 0; k < amplitude.size( ); ++k) {
            const bool edge = k == 0 || (n % 2 == 0 && k == n / 2);
            amplitude[k]    = std::abs(transformed[k]) * (edge ? 1 : 2) / gain;
        }
    }
}    // namespace execution
Spectrum spectrum(std::span< const double > x, double fs, bool remove_mean) {
    check(x, 2);
    rate(fs);
    const auto                      n = x.size( ), bins = n / 2 + 1;
    auto                            window = filtering::hann(n);
    std::vector< double >           buffer(n);
    std::vector< fourier::Complex > transformed(n);
    fourier::Plan                   plan(n);
    Spectrum                        out{ Array(bins), Array(bins), Array(bins) };
    execution::amplitude_spectrum(x, { out.amplitude.data( ), bins }, window, buffer, transformed, plan, remove_mean);
    for (std::size_t k = 0; k < bins; ++k) {
        const bool edge  = k == 0 || (n % 2 == 0 && k == n / 2);
        out.frequency[k] = static_cast< double >(k) * fs / n;
        out.power[k]     = out.amplitude[k] * out.amplitude[k] / (edge ? 1 : 2);
    }
    return out;
}
Stft stft(std::span< const double > x, double fs, int window, int overlap, int nfft) {
    check(x, 2);
    rate(fs);
    if (window < 2 || window > static_cast< int >(x.size( )) || overlap < 0 || overlap >= window || nfft < window)
        throw std::invalid_argument("invalid STFT window, overlap or transform size");
    const std::size_t               hop = window - overlap, edge = window / 2, extended = x.size( ) + 2 * edge;
    const std::size_t               frames = 1 + (extended - window + hop - 1) / hop, bins = nfft / 2 + 1;
    Stft                            out{ Array(frames), Array(bins), Matrix(bins, frames) };
    const auto                      w    = filtering::hann(window);
    const double                    gain = std::accumulate(w.begin( ), w.end( ), 0.0);
    fourier::Plan                   plan(nfft);
    std::vector< double >           buffer(nfft);
    std::vector< fourier::Complex > fft(nfft);
    for (std::size_t frame = 0; frame < frames; ++frame) {
        std::fill(buffer.begin( ), buffer.end( ), 0.0);
        for (int j = 0; j < window; ++j) {
            const auto index = static_cast< std::ptrdiff_t >(frame * hop + j) - static_cast< std::ptrdiff_t >(edge);
            if (index >= 0 && index < static_cast< std::ptrdiff_t >(x.size( ))) buffer[j] = x[index] * w[j];
        }
        plan.forward(buffer, fft);
        out.time[frame] = static_cast< double >(frame * hop) / fs;
        for (std::size_t k = 0; k < bins; ++k) {
            const bool terminal     = k == 0 || (nfft % 2 == 0 && k == static_cast< std::size_t >(nfft / 2));
            out.amplitude(k, frame) = std::abs(fft[k]) * (terminal ? 1 : 2) / gain;
        }
    }
    for (std::size_t k = 0; k < bins; ++k) out.frequency[k] = static_cast< double >(k) * fs / nfft;
    return out;
}
Array cepstrum(std::span< const double > x) {
    check(x, 2);
    auto                  window = filtering::hann(x.size( ));
    std::vector< double > a(x.size( )), y(x.size( ));
    for (std::size_t i = 0; i < x.size( ); ++i) a[i] = x[i] * window[i];
    fourier::Plan                   plan(x.size( ));
    std::vector< fourier::Complex > f(x.size( ));
    plan.forward(a, f);
    double mean = 0;
    for (std::size_t i = 0; i < x.size( ); ++i) {
        a[i] = std::log(std::abs(f[i]) + 1e-10);
        mean += a[i];
    }
    mean /= x.size( );
    for (std::size_t i = 0; i < x.size( ); ++i) f[i] = a[i] - mean;
    plan.inverse_real(f, y);
    return Eigen::Map< Array >(y.data( ), x.size( ) / 2);
}
Array hilbert_envelope(std::span< const double > x) {
    check(x);
    transforms::HilbertWorkspace w;
    w.prepare(x.size( ));
    std::vector< fourier::Complex > z(x.size( ));
    transforms::execution::analytic_signal(x, z, w);
    Array out(x.size( ));
    for (std::size_t i = 0; i < x.size( ); ++i) out[i] = std::abs(z[i]);
    return out;
}
Statistics statistics(std::span< const double > x, double floor) {
    check(x);
    return stats(x, floor);
}
TimeDomain time_domain(std::span< const double > x, double fs, int window, int step) {
    check(x);
    rate(fs);
    if (window < 1 || step < 0) throw std::invalid_argument("invalid statistics window");
    window                       = std::min(window, static_cast< int >(x.size( )));
    step                         = step ? std::min(step, window) : std::max(1, window / 2);
    const std::size_t     frames = 1 + (x.size( ) - window) / step;
    TimeDomain            out{ stats(x, 1e-12), Array(frames), Matrix(frames, 8), window, step };
    auto                  w = filtering::hann(window);
    std::vector< double > buffer(window);
    for (std::size_t k = 0; k < frames; ++k) {
        Eigen::Map< Array >(buffer.data( ), window) = Eigen::Map< const Array >(x.data( ) + k * step, window) * Eigen::Map< const Array >(w.data( ), window);
        const auto result                           = stats(buffer, 1e-12);
        out.time[k]                                 = static_cast< double >(k * step) / fs;
        for (int j = 0; j < 8; ++j) out.values(k, j) = result[j];
    }
    return out;
}
Matrix segmented_rms(std::span< const double > x, double fs, std::size_t segment, bool demean) {
    check(x);
    rate(fs);
    if (!segment) throw std::invalid_argument("segment must be positive");
    Matrix out((x.size( ) + segment - 1) / segment, 2);
    for (std::size_t start = 0, row = 0; start < x.size( ); start += segment, ++row) {
        const auto                size = std::min(segment, x.size( ) - start);
        Eigen::Map< const Array > block(x.data( ) + start, size);
        const double              mean = demean ? block.mean( ) : 0;
        out(row, 0)                    = (start + size * 0.5) / fs;
        out(row, 1)                    = std::sqrt((block - mean).square( ).mean( ));
    }
    return out;
}
Matrix extrema(std::span< const double > x, std::span< const double > y, std::size_t maximum) {
    if (x.size( ) != y.size( ) || maximum < 2) throw std::invalid_argument("invalid extrema coordinates or limit");
    std::vector< std::size_t > indices;
    if (y.size( ) <= maximum) {
        indices.resize(y.size( ));
        std::iota(indices.begin( ), indices.end( ), 0);
    } else {
        const auto block = (y.size( ) + maximum / 2 - 1) / (maximum / 2);
        for (std::size_t start = 0; start < y.size( ); start += block) {
            auto first = y.begin( ) + start, last = y.begin( ) + std::min(y.size( ), start + block);
            auto lo = std::min_element(first, last) - y.begin( ), hi = std::max_element(first, last) - y.begin( );
            indices.push_back(std::min(lo, hi));
            if (lo != hi) indices.push_back(std::max(lo, hi));
        }
    }
    Matrix out(indices.size( ), 2);
    for (std::size_t i = 0; i < indices.size( ); ++i) {
        out(i, 0) = x[indices[i]];
        out(i, 1) = y[indices[i]];
    }
    return out;
}
Array autocorrelation(std::span< const double > x, bool demean) {
    check(x);
    std::size_t n = 1;
    while (n < 2 * x.size( ) - 1) n *= 2;
    std::vector< double > input(n, 0), output(n);
    const double          mean = demean ? Eigen::Map< const Array >(x.data( ), x.size( )).mean( ) : 0;
    for (std::size_t i = 0; i < x.size( ); ++i) input[i] = x[i] - mean;
    fourier::Plan                   plan(n);
    std::vector< fourier::Complex > f(n);
    plan.forward(input, f);
    for (auto &v : f) v = std::norm(v);
    plan.inverse_real(f, output);
    return Eigen::Map< Array >(output.data( ), x.size( ));
}
}    // namespace cnn_compute::numeric
