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
    // abs/centered 物化一次（发现7）：各统计量复用同一份数据，调用方提供窗长临时，
    // 帧循环可跨帧复用；归约次序不变，与逐次求值的表达式逐位一致。
    Statistics stats(std::span< const double > x, double floor, std::span< double > abs_store,
                     std::span< double > centered_store) {
        const Eigen::Map< const Array > a(x.data( ), x.size( ));
        const double                    mean = a.mean( );
        Eigen::Map< Array >             abs(abs_store.data( ), x.size( ));
        Eigen::Map< Array >             centered(centered_store.data( ), x.size( ));
        abs               = a.abs( );
        centered          = a - mean;
        const double peak = abs.maxCoeff( ), rms = std::sqrt(a.square( ).mean( ));
        const double mean_abs = abs.mean( ), mean_sqrt = (abs + floor).sqrt( ).mean( );
        const double variance  = centered.square( ).mean( );
        const double threshold = std::numeric_limits< double >::epsilon( ) * std::abs(mean);
        double       kurt = std::numeric_limits< double >::quiet_NaN( ), skew = kurt;
        if (variance > threshold * threshold) {
            kurt = centered.square( ).square( ).mean( ) / (variance * variance);
            skew = centered.cube( ).mean( ) / std::pow(variance, 1.5);
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
        plan.forward_half(buffer, transformed.first(x.size( ) / 2 + 1));
        // 幅值统一 sqrt(re²+im²)（工单A1，#144-发现2）：MSVC 的 abs(complex) 走 hypot，
        // 2-5× 于 sqrt；物理幅值不涉溢保护区（|x|>~1e154），末位差异在冻结预算内。
        for (std::size_t k = 0; k < amplitude.size( ); ++k) {
            const bool edge = k == 0 || (n % 2 == 0 && k == n / 2);
            amplitude[k]    = std::sqrt(std::norm(transformed[k])) * (edge ? 1 : 2) / gain;
        }
    }
}    // namespace execution
Spectrum spectrum(std::span< const double > x, double fs, bool remove_mean) {
    check(x, 2);
    rate(fs);
    const auto                      n = x.size( ), bins = n / 2 + 1;
    auto                            window = filtering::hann_table(n);    // 全长 Hann 进程槽（发现1）
    std::vector< double >           buffer(n);
    std::vector< fourier::Complex > transformed(bins);
    fourier::Plan                   plan(n);    // 计划进程槽，同尺寸零重建（发现1/4）
    Spectrum                        out{ Array(bins), Array(bins), Array(bins) };
    execution::amplitude_spectrum(x, { out.amplitude.data( ), bins }, window->values, buffer,
                                  transformed, plan, remove_mean);
    // 频率 (k*fs)/n 与幂 a²/2（DC/偶 Nyquist 端点覆写）元素级一次生成（发现7）。
    out.frequency = Array::LinSpaced(bins, 0.0, static_cast< double >(bins - 1)) * fs
                    / static_cast< double >(n);
    out.power     = out.amplitude * out.amplitude / 2.0;
    out.power[0]  = out.amplitude[0] * out.amplitude[0];
    if (n % 2 == 0) out.power[n / 2] = out.amplitude[n / 2] * out.amplitude[n / 2];
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
    std::vector< fourier::Complex > fft(bins);
    // 循环前一次清零（发现6）：nfft 尾部恒为零；帧内越界位置——首部由初值保持、
    // 尾部随右端收缩逐帧回零，替代原先的每帧全量清零。
    std::fill(buffer.begin( ), buffer.end( ), 0.0);
    const auto size = static_cast< std::ptrdiff_t >(x.size( ));
    for (std::size_t frame = 0; frame < frames; ++frame) {
        const auto base = static_cast< std::ptrdiff_t >(frame * hop) - static_cast< std::ptrdiff_t >(edge);
        const auto lo   = std::max< std::ptrdiff_t >(0, -base);
        const auto hi   = std::min< std::ptrdiff_t >(window, size - base);
        if (hi < window) std::fill(buffer.begin( ) + hi, buffer.begin( ) + window, 0.0);
        for (auto j = lo; j < hi; ++j) buffer[j] = x[base + j] * w[j];
        plan.forward_half(buffer, fft);
        out.time[frame] = static_cast< double >(frame * hop) / fs;
        for (std::size_t k = 0; k < bins; ++k) {
            const bool terminal     = k == 0 || (nfft % 2 == 0 && k == static_cast< std::size_t >(nfft / 2));
            out.amplitude(k, frame) = std::sqrt(std::norm(fft[k])) * (terminal ? 1 : 2) / gain;
        }
    }
    out.frequency = Array::LinSpaced(bins, 0.0, static_cast< double >(bins - 1)) * fs
                    / static_cast< double >(nfft);
    return out;
}
Array cepstrum(std::span< const double > x) {
    check(x, 2);
    const auto            n      = x.size( );
    auto                  window = filtering::hann_table(n);    // 全长 Hann 进程槽（发现1）
    std::vector< double > a(n), y(n);
    Eigen::Map< Array >(a.data( ), n) = Eigen::Map< const Array >(x.data( ), n)
                                        * Eigen::Map< const Array >(window->values.data( ), n);    // 窗乘元素级（发现7）
    fourier::Plan                   plan(n);
    std::vector< fourier::Complex > f(n);
    plan.forward(a, f);
    double mean = 0;
    for (std::size_t i = 0; i < n; ++i) {
        a[i] = std::log(std::sqrt(std::norm(f[i])) + 1e-10);
        mean += a[i];
    }
    mean /= n;
    for (std::size_t i = 0; i < n; ++i) f[i] = a[i] - mean;
    plan.inverse_real(f, y);
    return Eigen::Map< Array >(y.data( ), n / 2);
}
Array hilbert_envelope(std::span< const double > x) {
    check(x);
    transforms::HilbertWorkspace w;
    w.prepare(x.size( ));
    const auto z = transforms::execution::analytic_signal(x, w);    // 工作区 analytic 缓冲，免局部 z（发现5）
    Array      out(x.size( ));
    for (std::size_t i = 0; i < x.size( ); ++i) out[i] = std::sqrt(std::norm(z[i]));
    return out;
}
Statistics statistics(std::span< const double > x, double floor) {
    check(x);
    if (!std::isfinite(floor) || floor < 0) throw std::invalid_argument("margin floor must be finite and nonnegative");
    std::vector< double > abs(x.size( )), centered(x.size( ));
    return stats(x, floor, abs, centered);
}
TimeDomain time_domain(std::span< const double > x, double fs, int window, int step) {
    check(x);
    rate(fs);
    if (window < 1 || step < 0) throw std::invalid_argument("invalid statistics window");
    window                       = std::min(window, static_cast< int >(x.size( )));
    step                         = step ? std::min(step, window) : std::max(1, window / 2);
    const std::size_t     frames = 1 + (x.size( ) - window) / step;
    std::vector< double > abs(x.size( )), centered(x.size( ));    // 总体与帧统计共用（发现7）
    TimeDomain            out{ stats(x, 1e-12, abs, centered), Array(frames), Matrix(frames, 8), window, step };
    auto                  w = filtering::hann(window);
    std::vector< double > buffer(window);
    for (std::size_t k = 0; k < frames; ++k) {
        Eigen::Map< Array >(buffer.data( ), window) = Eigen::Map< const Array >(x.data( ) + k * step, window) * Eigen::Map< const Array >(w.data( ), window);
        const auto result                           = stats(buffer, 1e-12, { abs.data( ), static_cast< std::size_t >(window) },
                                                            { centered.data( ), static_cast< std::size_t >(window) });
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
    fourier::Plan                   plan(n);    // 计划进程槽（发现1）；逆变换经原位打包（发现8）
    std::vector< fourier::Complex > f(n / 2 + 1);
    plan.forward_half(input, f);
    for (auto &v : f) v = std::norm(v);
    plan.inverse_half(f, output);
    return Eigen::Map< Array >(output.data( ), x.size( ));
}
}    // namespace cnn_compute::numeric
