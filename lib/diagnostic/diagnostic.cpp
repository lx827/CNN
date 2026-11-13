#include <diagnostic/api.hpp>
#include <filtering/api.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <numbers>
#include <numeric>
#include <stdexcept>

namespace cnn_compute::diagnostic {
constexpr double pi = std::numbers::pi_v< double >;
namespace {
    void valid(std::span< const double > x, std::size_t minimum) {
        if (x.size( ) < minimum) throw std::invalid_argument("输入样本不足");
        for (double v : x)
            if (!std::isfinite(v)) throw std::invalid_argument("输入必须有限");
    }
    void sample_rate(double fs) {
        if (!std::isfinite(fs) || fs <= 0) throw std::invalid_argument("采样率必须有限且为正");
    }
    double mean(std::span< const double > x) {
        return std::accumulate(x.begin( ), x.end( ), 0.0) / x.size( );
    }
    std::span< double > writable(core::Array &x) {
        return { x.data( ), static_cast< std::size_t >(x.size( )) };
    }
    void window(Workspace &w, std::size_t n) {
        // 与 filtering::hann 同一公式源（0.5-0.5*cos(2πi/n)）；sc_scoh/MSB 的段长远短
        // 于全长窗，按 filtering 契约直接取 hann，不占进程级 Hann 表槽。
        w.window = filtering::hann(n);
    }
    std::size_t segments(std::size_t n, std::size_t l, std::size_t step, std::size_t minimum) {
        if (l < 32 || l > n || !step || (n - l) / step + 1 < minimum) throw std::invalid_argument("insufficient_segments");
        return (n - l) / step + 1;
    }
    double quantile(std::vector< double > &values, double p) {
        const double position = p * (values.size( ) - 1);
        const auto   lo = static_cast< std::size_t >(position), hi = static_cast< std::size_t >(std::ceil(position));
        std::nth_element(values.begin( ), values.begin( ) + lo, values.end( ));
        const double a = values[lo];
        if (lo == hi) return a;
        std::nth_element(values.begin( ) + lo + 1, values.begin( ) + hi, values.end( ));
        return a + (values[hi] - a) * (position - lo);
    }
    // 谱峭度双遍执行核，公开入口与 kurtogram 共用：第一遍有限检查与 |z| 最大值
    // （magnitudes 非空时同步填充幅值数组，scale 同时就是 kurtogram 的谱峰），
    // 第二遍按元素序累加 power/fourth，各累加次序与逐遍写法一致。
    double spectral_kurtosis(std::span< const Complex > x, std::span< double > magnitudes, double &scale) {
        scale = 0;
        for (std::size_t i = 0; i < x.size( ); ++i) {
            if (!std::isfinite(x[i].real( )) || !std::isfinite(x[i].imag( ))) throw std::invalid_argument("复输入必须有限");
            const double magnitude = std::sqrt(std::norm(x[i]));    // hypot→sqrt（工单A1，#145-发现3(d)）
            if (i < magnitudes.size( )) magnitudes[i] = magnitude;
            scale = std::max(scale, magnitude);
        }
        if (scale == 0) throw std::domain_error("零能量频带无法估计谱峭度");
        double power = 0, fourth = 0;
        for (std::size_t i = 0; i < x.size( ); ++i) {
            double p = std::norm(x[i] / scale);
            power += p;
            fourth += p * p;
        }
        return x.size( ) * fourth / (power * power) - 2;
    }
}    // namespace
void Workspace::prepare(std::size_t n) {
    plan.prepare(n);
    window.resize(n);
    real.resize(n);
    modulated.resize(n);
    first.resize(n);
    second.resize(n);
    phases.resize(n);
    temporary.resize(n);
    low_power.resize(n / 2 + 1);
    high_power.resize(n / 2 + 1);
}
namespace execution {
    void teager(std::span< const double > x, std::span< double > y) {
        y.front( ) = x.front( ) * x.front( );
        y.back( )  = x.back( ) * x.back( );
        if (x.size( ) > 2) {
            core::Map a(x.data( ) + 1, x.size( ) - 2), left(x.data( ), x.size( ) - 2), right(x.data( ) + 2, x.size( ) - 2);
            Eigen::Map< core::Array >(y.data( ) + 1, y.size( ) - 2) = a.square( ) - left * right;
        }
    }
    void cepstral_prewhiten(std::span< const double > x, double fs, std::span< const double > comb,
                            double width, std::span< double > output, Workspace &w) {
        const auto   n      = x.size( );
        const double offset = mean(x);
        for (std::size_t i = 0; i < n; ++i) w.real[i] = x[i] - offset;
        w.plan.forward(w.real, w.first);
        double peak = 0;
        for (auto z : w.first) peak = std::max(peak, std::abs(z));
        if (peak == 0) throw std::domain_error("零能量信号无法倒谱预白化");
        const double floor   = peak * 1e-10;
        double       minimum = std::numeric_limits< double >::infinity( ), maximum = -minimum;
        for (std::size_t i = 0; i < n; ++i) {
            double value = std::log(std::max(std::abs(w.first[i]), floor));
            w.second[i]  = value;
            minimum      = std::min(minimum, value);
            maximum      = std::max(maximum, value);
        }
        w.plan.inverse_real(w.second, w.real);
        for (double fundamental : comb) {
            const double base  = fs / fundamental;
            const int    count = static_cast< int >(n / (2 * base));
            for (int harmonic = 1; harmonic <= count; ++harmonic) {
                const double center = harmonic * base;
                const auto   half   = std::max(1L, static_cast< long >(std::nearbyint(center * width / 2)));
                const auto   left = static_cast< long >(std::floor(center)) - half, right = static_cast< long >(std::ceil(center)) + half;
                if (left < 1 || right >= static_cast< long >(n / 2) - 1) continue;
                for (int sign : { 1, -1 }) {
                    auto         index = [&](long i) { return static_cast< std::size_t >((sign * i + static_cast< long >(n)) % static_cast< long >(n)); };
                    const double a = w.real[index(left - 1)], b = w.real[index(right + 1)];
                    for (long i = left; i <= right; ++i) {
                        double weight    = double(i - left + 1) / (right - left + 2);
                        w.real[index(i)] = a * (1 - weight) + b * weight;
                    }
                }
            }
        }
        w.plan.forward(w.real, w.second);
        for (std::size_t i = 0; i < n; ++i) w.second[i] = std::polar(std::exp(std::clamp(w.second[i].real( ), minimum - 2, maximum + 2)), std::arg(w.first[i]));
        w.plan.inverse_real(w.second, output);
    }
    void sc_scoh(std::span< const double > x, double fs, std::span< const double > alpha, std::size_t l,
                 std::size_t step, CyclicResult &out, Workspace &w) {
        std::fill(out.correlation.begin( ), out.correlation.end( ), Complex{});
        const double offset      = mean(x);
        double       input_scale = 0;
        for (double v : x) input_scale = std::max(input_scale, std::abs(v - offset));
        out.input_scale = input_scale;
        window(w, l);
        double scale = 0;
        for (double v : w.window) scale += v * v;
        scale *= fs;
        const auto bins = l / 2 + 1, count = out.segments;
        // PSD只需两条carrier轴；复结果直接累加到最终拥有者。
        auto &low_power  = w.low_power;
        auto &high_power = w.high_power;
        if (w.phases.size( ) != x.size( )) w.phases.resize(x.size( ));    // 相位表按信号全长准备
        for (std::size_t a = 0; a < alpha.size( ); ++a) {
            // 相位角只依赖全局采样序号：一次建 n 长表，段循环查表（表达式与逐次
            // polar 完全相同，逐位一致）；sincos 从 alpha×count×l 降为 alpha×n。
            for (std::size_t i = 0; i < x.size( ); ++i) w.phases[i] = std::polar(1.0, pi * alpha[a] * i / fs);
            std::fill(low_power.begin( ), low_power.end( ), 0);
            std::fill(high_power.begin( ), high_power.end( ), 0);
            auto *corr = out.correlation.data( ) + a * bins;
            for (std::size_t segment = 0; segment < count; ++segment) {
                const auto start = segment * step;
                for (std::size_t j = 0; j < l; ++j) {
                    double  value  = (x[start + j] - offset) * (input_scale > 0 ? 1 / input_scale : 1) * w.window[j];
                    Complex phase  = w.phases[start + j];
                    w.modulated[j] = value * phase;
                    w.temporary[j] = value * std::conj(phase);
                }
                w.plan.forward(w.modulated, w.first);
                w.plan.forward(w.temporary, w.second);
                for (std::size_t k = 0; k < bins; ++k) {
                    corr[k] += w.first[k] * std::conj(w.second[k]);
                    low_power[k] += std::norm(w.first[k]);
                    high_power[k] += std::norm(w.second[k]);
                }
            }
            for (std::size_t k = 0; k < bins; ++k) {
                double coherence = 0;
                if (low_power[k] > 0 && high_power[k] > 0) {
                    double amplitude = std::abs(corr[k]) / std::sqrt(low_power[k]) / std::sqrt(high_power[k]);
                    coherence        = amplitude * amplitude;
                }
                out.coherence[a * bins + k] = std::clamp(coherence, 0.0, 1.0);
                corr[k] *= input_scale * input_scale / (scale * count);
            }
        }
    }
    void modulation_bispectrum(std::span< const double > x, double fs, std::span< const double > carriers,
                               std::span< const double > modulation, std::size_t l, std::size_t step,
                               MSBResult &out, Workspace &w) {
        std::fill(out.mean.begin( ), out.mean.end( ), Complex{});
        window(w, l);
        const double gain  = std::accumulate(w.window.begin( ), w.window.end( ), 0.0);
        const double df    = fs / l;
        const auto   cells = carriers.size( ) * modulation.size( );
        // 网格容量在执行准备阶段增长；同规模后续调用复用，不在分段循环分配。
        w.center_bins.resize(cells);
        w.upper_bins.resize(cells);
        w.lower_bins.resize(cells);
        auto &center = w.center_bins;
        auto &upper  = w.upper_bins;
        auto &lower  = w.lower_bins;
        w.low_power.assign(cells, 0);
        w.high_power.assign(cells, 0);
        auto &side_power    = w.low_power;
        auto &carrier_power = w.high_power;
        for (std::size_t i = 0; i < carriers.size( ); ++i)
            for (std::size_t j = 0; j < modulation.size( ); ++j) {
                auto index       = i * modulation.size( ) + j;
                center[index]    = static_cast< int >(std::nearbyint(carriers[i] / df));
                int m            = static_cast< int >(std::nearbyint(modulation[j] / df));
                upper[index]     = center[index] + m;
                lower[index]     = center[index] - m;
                out.valid[index] = lower[index] >= 1 && upper[index] <= static_cast< int >(l / 2) && m >= 1
                                   && carriers[i] + modulation[j] <= fs / 2 && carriers[i] - modulation[j] > 0;
            }
        for (std::size_t s = 0; s < out.segments; ++s) {
            const auto start  = s * step;
            double     offset = 0;
            for (std::size_t j = 0; j < l; ++j) offset += x[start + j];
            offset /= l;
            for (std::size_t j = 0; j < l; ++j) w.real[j] = (x[start + j] - offset) * w.window[j] / gain;
            w.plan.forward(w.real, w.first);
            for (std::size_t i = 0; i < cells; ++i)
                if (out.valid[i]) {
                    Complex side = w.first[upper[i]] * w.first[lower[i]], c = w.first[center[i]] * w.first[center[i]];
                    out.mean[i] += side * std::conj(c);
                    side_power[i] += std::norm(side);
                    carrier_power[i] += std::norm(c);
                }
        }
        const double nan = std::numeric_limits< double >::quiet_NaN( );
        for (std::size_t i = 0; i < cells; ++i) {
            if (!out.valid[i]) {
                out.mean[i]      = { nan, nan };
                out.coherence[i] = nan;
                continue;
            }
            const double denominator = std::sqrt(side_power[i]) * std::sqrt(carrier_power[i]);
            out.coherence[i]         = denominator > 0 ? std::min(1.0, std::abs(out.mean[i]) / denominator) : nan;
            out.mean[i] /= out.segments;
        }
    }
}    // namespace execution
core::Array teager(std::span< const double > x) {
    valid(x, 3);
    core::Array out(x.size( ));
    execution::teager(x, writable(out));
    return out;
}
double complex_spectral_kurtosis(std::span< const Complex > x) {
    if (x.size( ) < 2) throw std::invalid_argument("谱峭度至少两个复样本");
    double scale = 0;
    return spectral_kurtosis(x, {}, scale);
}
core::Array cepstral_prewhiten(std::span< const double > x, double fs, std::span< const double > comb, double width) {
    valid(x, 256);
    sample_rate(fs);
    if (comb.empty( ) || !std::isfinite(width) || width <= 0 || width > 0.1) throw std::invalid_argument("CPW梳状频率或宽度无效");
    for (double f : comb)
        if (!std::isfinite(f) || f <= 0 || f >= fs / 2) throw std::invalid_argument("CPW频率必须位于(0,Nyquist)");
    Workspace w;
    w.prepare(x.size( ));
    core::Array out(x.size( ));
    execution::cepstral_prewhiten(x, fs, comb, width, writable(out), w);
    return out;
}
CyclicResult sc_scoh(std::span< const double > x, double fs, std::span< const double > alpha, std::size_t l, std::size_t step) {
    valid(x, 128);
    sample_rate(fs);
    const auto count = segments(x.size( ), l, step, 4);
    if (alpha.empty( )) throw std::invalid_argument("必须提供循环频率");
    for (double a : alpha)
        if (!std::isfinite(a) || a < 0 || a > fs / 2) throw std::invalid_argument("循环频率必须位于[0,Nyquist]");
    const auto   bins = l / 2 + 1;
    CyclicResult r{ alpha.size( ), bins, count, 0, std::vector< Complex >(alpha.size( ) * bins), std::vector< double >(alpha.size( ) * bins) };
    Workspace    w;
    w.prepare(l);
    execution::sc_scoh(x, fs, alpha, l, step, r, w);
    return r;
}
MSBResult modulation_bispectrum(std::span< const double > x, double fs, std::span< const double > carriers,
                                std::span< const double > modulation, std::size_t l, std::size_t step, std::size_t minimum) {
    valid(x, 1);
    sample_rate(fs);
    const auto count = segments(x.size( ), l, step, std::max< std::size_t >(minimum, 2));
    if (carriers.empty( ) || modulation.empty( ) || carriers.size( ) * modulation.size( ) > 16384) throw std::invalid_argument("MSB网格无效");
    for (auto axis : { carriers, modulation })
        for (double f : axis)
            if (!std::isfinite(f) || f <= 0 || f > fs / 2) throw std::invalid_argument("MSB频率必须位于(0,Nyquist]");
    const auto cells = carriers.size( ) * modulation.size( );
    MSBResult  r{ carriers.size( ), modulation.size( ), count, std::vector< Complex >(cells), std::vector< double >(cells), std::vector< unsigned char >(cells) };
    Workspace  w;
    w.prepare(l);
    execution::modulation_bispectrum(x, fs, carriers, modulation, l, step, r, w);
    return r;
}
std::vector< BandStatistics > filter_bank_kurtogram(std::span< const double > x, double fs, int max_level, double min_frequency, int order) {
    valid(x, 256);
    sample_rate(fs);
    if (max_level < 1 || max_level > 6 || order < 1 || !std::isfinite(min_frequency) || min_frequency <= 0 || min_frequency >= fs / 2)
        throw std::invalid_argument("谱峭度滤波器组参数无效");
    std::vector< double > centered(x.begin( ), x.end( ));
    const double          offset = mean(x);
    for (double &v : centered) v -= offset;
    Workspace w;
    w.prepare(x.size( ));
    std::vector< BandStatistics > out;
    const auto                    n    = x.size( );
    std::size_t                   edge = std::max< std::size_t >(8, n / 20);
    if (n <= 2 * edge + 16) edge = 0;
    std::vector< double > magnitude(n - 2 * edge), filtered(n);
    for (int level = 1; level <= max_level; ++level) {
        double width = (fs / 2) / (1 << level);
        for (int index = 0; index < (1 << level); ++index) {
            double low = std::max(index * width, min_frequency), high = std::min((index + 1) * width, fs / 2 * (1 - 1e-8));
            if (high - low < std::max(2.0, width * 0.05)) continue;
            auto coefficients = filtering::butterworth(order, low, high, fs);
            filtering::execution::sosfiltfilt(centered, coefficients, filtered, w.filtering);
            double peak = 0;
            for (double value : filtered) peak = std::max(peak, std::abs(value));
            if (peak == 0) continue;
            // 半谱即可：forward 的共轭填充半谱随即被清零，纯浪费的 2n 复写。
            w.plan.forward_half(filtered, { w.first.data( ), n / 2 + 1 });
            for (std::size_t k = 1; k < (n + 1) / 2; ++k) w.first[k] *= 2;
            for (std::size_t k = n / 2 + 1; k < n; ++k) w.first[k] = 0;
            w.plan.inverse(w.first, w.second);
            std::span< const Complex > core(w.second.data( ) + edge, n - 2 * edge);
            double                     scale = 0;
            // |z| 的最大值、幅值数组与谱峰同遍产出，power/fourth 第二遍按元素序累加。
            const double sk   = spectral_kurtosis(core, { magnitude.data( ), core.size( ) }, scale);
            peak              = scale;
            double median     = std::max(quantile(magnitude, 0.5), peak * std::numeric_limits< double >::epsilon( ));
            double percentile = quantile(magnitude, 0.95);
            out.push_back({ low, high, level, sk, peak / median, percentile / median });
        }
    }
    if (out.empty( )) throw std::domain_error("没有有效频带可估计谱峭度");
    return out;
}
}    // namespace cnn_compute::diagnostic
