#include "api.hpp"
#include <filtering/api.hpp>
#include <sequence/api.hpp>
#include <transforms/hilbert.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <numbers>
#include <stdexcept>

namespace cnn_compute::rotation {
namespace {
    // 一次调用内全部候选共享的执行资源：n 长半谱计划与缓冲、2^k 自相关计划与
    // 缓冲、带通/Hilbert 工作区。构造处按信号长度一次准备，候选间零重复计划/
    // 缓冲构建；实例为单个活跃调用独占，不跨调用共享可写状态。
    struct SpeedWorkspace {
        fourier::Plan                   plan;           // n：三处幅值谱
        fourier::Plan                   correlation;    // 2^k：自相关
        filtering::Workspace            filtering;      // 带通候选共用
        transforms::HilbertWorkspace    hilbert;        // 包络候选共用
        std::size_t                     samples = 0, padded = 0;
        std::vector< fourier::Complex > half, analytic, correlation_half;
        std::vector< double >           amplitude, band, correlation_buffer;
        void                            prepare(std::size_t n) {
            samples = n;
            plan.prepare(n);
            half.resize(n / 2 + 1);
            amplitude.resize(n / 2 + 1);
            analytic.resize(n);
            band.resize(n);
            hilbert.prepare(n);
            padded = 1;
            while (padded < 2 * n - 1) padded *= 2;
            correlation.prepare(padded);
            correlation_buffer.resize(padded);
            correlation_half.resize(padded / 2 + 1);
        }
    };
    double median(std::vector< double > &a) {
        if (a.empty( )) return 0.;
        auto k = a.size( ) / 2;
        std::nth_element(a.begin( ), a.begin( ) + k, a.end( ));
        double m = a[k];
        if (a.size( ) % 2 == 0) m = (m + *std::max_element(a.begin( ), a.begin( ) + k)) * .5;
        return m;
    }
    std::vector< double > centered(std::span< const double > x, double fs) {
        if (x.empty( ) || !std::isfinite(fs) || fs <= 0) throw std::invalid_argument("invalid sampling rate or empty signal");
        for (double v : x)
            if (!std::isfinite(v)) throw std::invalid_argument("signal must be finite");
        double                m = core::Map(x.data( ), x.size( )).mean( );
        std::vector< double > y(x.size( ));
        for (std::size_t i = 0; i < x.size( ); ++i) y[i] = x[i] - m;
        return y;
    }
    void search_range(double low, double high) {
        if (!std::isfinite(low) || !std::isfinite(high) || low <= 0 || high <= low) throw std::invalid_argument("invalid speed search range");
    }
    // 4 阶双向带通写入共享 band 缓冲；带通条件不满足时原样借用输入（只读）。
    std::span< const double > bandpass(std::span< const double > x, double fs, double low, double high, SpeedWorkspace &w) {
        if (x.size( ) < 28 || low <= 0 || high >= fs / 2 || low >= high) return x;
        auto sos = filtering::butterworth(4, low, high, fs);
        filtering::execution::sosfiltfilt(x, sos, { w.band.data( ), x.size( ) }, w.filtering);
        return { w.band.data( ), x.size( ) };
    }
    // 半谱幅值：与全谱 forward 的前半逐位相同，幅值循环只读 n/2+1；out 与 half/x 不重叠。
    void magnitude(std::span< const double > x, std::span< double > out, SpeedWorkspace &w) {
        w.plan.forward_half(x, { w.half.data( ), out.size( ) });
        // 幅值统一 sqrt(re²+im²)（工单A1，#145-发现5）：hypot→sqrt，末位差异在冻结预算内。
        for (std::size_t i = 0; i < out.size( ); ++i) out[i] = std::sqrt(std::norm(w.half[i]));
    }
    int peak(std::span< const double > a, double df, double low, double high) {
        int start = std::max(0, static_cast< int >(std::ceil(low / df))), stop = std::min(static_cast< int >(a.size( )) - 1, static_cast< int >(std::floor(high / df)));
        if (start > stop) return -1;
        return static_cast< int >(std::max_element(a.begin( ) + start, a.begin( ) + stop + 1) - a.begin( ));
    }
    double parabolic(std::span< const double > a, int j, double df) {
        if (j <= 0 || j >= static_cast< int >(a.size( )) - 1) return j * df;
        double p = a[j - 1], q = a[j], r = a[j + 1], den = p - 2 * q + r;
        if (den == 0 || q <= std::max(p, r)) return j * df;
        return (j + .5 * (p - r) / den) * df;
    }
    bool no_variation(std::span< const double > x) {
        return std::sqrt(core::Map(x.data( ), x.size( )).square( ).mean( )) <= std::numeric_limits< double >::epsilon( );
    }
}    // namespace
namespace {
    // 上层已建立有限、中心化输入及搜索范围；组合候选共享同一 SpeedWorkspace，
    // 不再反复验证/减均值，也不再逐候选重建计划、工作区与全谱缓冲。
    SpeedResult envelope_prepared(std::span< const double > x, double fs, double carrier, double low, double high, double bandwidth, SpeedWorkspace &w) {
        double l = std::max(low, carrier - bandwidth), h = std::min(fs / 2 - 1e-6, carrier + bandwidth);
        if (x.size( ) < 32 || l >= h) return { 0, "envelope", "包络频带或信号长度无效" };
        auto filtered = bandpass(x, fs, l, h, w);
        transforms::execution::analytic_signal(filtered, { w.analytic.data( ), x.size( ) }, w.hilbert);
        auto   envelope = std::span< double >(w.band.data( ), x.size( ));    // 包络写回带通缓冲，与原实现同块复用
        double mean     = 0.;
        for (std::size_t i = 0; i < x.size( ); ++i) {
            envelope[i] = std::sqrt(std::norm(w.analytic[i]));
            mean += envelope[i];
        }
        mean /= x.size( );
        for (double &v : envelope) v -= mean;
        magnitude(envelope, { w.amplitude.data( ), w.amplitude.size( ) }, w);
        int index = peak({ w.amplitude.data( ), w.amplitude.size( ) }, fs / x.size( ), low, high);
        if (index < 0 || w.amplitude[index] <= std::numeric_limits< double >::epsilon( )) return { 0, "envelope", "包络谱搜索范围内无谱峰" };
        return { index * fs / x.size( ), "envelope", {} };
    }
    SpeedResult autocorrelation_prepared(std::span< const double > x, double fs, double low, double high, SpeedWorkspace &w) {
        double h = std::min(fs / 2 - 1e-6, std::max(high * 6, high + 20)), l = std::max(1e-6, low * .5);
        auto   y = bandpass(x, fs, l, h, w);
        // 与 numeric::autocorrelation(y,false) 同式：2^k 零填充、半谱模平方、逆半变换；
        // 计划与缓冲来自共享工作区，免公开入口的重复 finite 扫描与逐次重建。
        std::copy(y.begin( ), y.end( ), w.correlation_buffer.begin( ));
        std::fill(w.correlation_buffer.data( ) + y.size( ), w.correlation_buffer.data( ) + w.padded, 0.);
        w.correlation.forward_half({ w.correlation_buffer.data( ), w.padded }, { w.correlation_half.data( ), w.correlation_half.size( ) });
        for (auto &v : w.correlation_half) v = std::norm(v);
        w.correlation.inverse_half(w.correlation_half, { w.correlation_buffer.data( ), w.padded });
        auto padded = std::span< double >(w.correlation_buffer.data( ), y.size( ));
        if (padded[0] <= 0) return { 0, "autocorrelation", "零滞后自相关无效" };
        double normalization = padded[0];
        for (std::size_t i = 0; i < y.size( ); ++i) padded[i] /= normalization;
        int start = std::max(1, static_cast< int >(fs / high)), stop = std::min(static_cast< int >(y.size( )) - 1, static_cast< int >(fs / low));
        if (stop <= start) return { 0, "autocorrelation", "搜索范围对应的滞后区间为空" };
        int    best            = static_cast< int >(std::max_element(padded.begin( ) + start, padded.begin( ) + stop + 1) - padded.begin( ));
        double prominence_best = -1;
        for (int j = start + 1; j < stop; ++j) {
            if (padded[j] <= padded[j - 1] || padded[j] < padded[j + 1]) continue;
            int end = j;
            while (end < stop && padded[end + 1] == padded[j]) ++end;
            if (end == stop) continue;
            double left = padded[j], right = padded[j];
            for (int k = j - 1; k >= start && padded[k] <= padded[j]; --k) left = std::min(left, padded[k]);
            for (int k = end + 1; k <= stop && padded[k] <= padded[j]; ++k) right = std::min(right, padded[k]);
            double p = padded[j] - std::max(left, right);
            if (p >= .03 && p > prominence_best) {
                prominence_best = p;
                best            = (j + end) / 2;
            }
            j = end;
        }
        return { fs / best, "autocorrelation", {} };
    }
}    // namespace
SpeedResult envelope_speed(std::span< const double > x, double fs, double carrier, double low, double high, double bandwidth) {
    if (!std::isfinite(carrier) || !std::isfinite(bandwidth) || bandwidth <= 0) throw std::invalid_argument("invalid envelope carrier or bandwidth");
    search_range(low, high);
    auto           y = centered(x, fs);
    SpeedWorkspace w;
    w.prepare(y.size( ));
    return envelope_prepared(y, fs, carrier, low, high, bandwidth, w);
}
SpeedResult autocorrelation_speed(std::span< const double > x, double fs, double low, double high) {
    search_range(low, high);
    auto y = centered(x, fs);
    if (y.size( ) < 16 || no_variation(y)) return { 0, "autocorrelation", "信号过短或没有有效变化" };
    SpeedWorkspace w;
    w.prepare(y.size( ));
    return autocorrelation_prepared(y, fs, low, high, w);
}
SpeedResult spectrum_speed(std::span< const double > x, double fs, double low, double high, int harmonics, double bandwidth, double smooth) {
    search_range(low, high);
    auto y = centered(x, fs);
    if (y.size( ) < 32 || no_variation(y)) return { 0, "spectrum_arbitration", "信号过短或没有有效变化" };
    if (harmonics < 1 || !std::isfinite(bandwidth) || !std::isfinite(smooth) || bandwidth <= 0 || smooth < 0) throw std::invalid_argument("invalid spectral speed parameters");
    // 初谱全程参与仲裁（supported/背景中位数），候选的幅值谱走共享缓冲。
    SpeedWorkspace resources;
    resources.prepare(y.size( ));
    std::vector< double > a(y.size( ) / 2 + 1);
    magnitude(y, a, resources);
    double df     = fs / y.size( );
    int    kernel = std::max(1, static_cast< int >(std::nearbyint(smooth / df)));
    if (kernel > 1) {
        std::vector< double > prefix(a.size( ) + 1);
        for (std::size_t i = 0; i < a.size( ); ++i) prefix[i + 1] = prefix[i] + a[i];
        for (int i = 0; i < static_cast< int >(a.size( )); ++i) {
            int l = std::max(0, i - kernel / 2), h = std::min(static_cast< int >(a.size( )), i + (kernel - 1) / 2 + 1);
            a[i] = (prefix[h] - prefix[l]) / kernel;
        }
    }
    double maximum = *std::max_element(a.begin( ), a.end( ));
    if (maximum <= std::numeric_limits< double >::epsilon( )) return { 0, "spectrum_arbitration", "频谱没有非零分量" };
    for (double &v : a) v /= maximum;
    int start = std::max(0, static_cast< int >(std::ceil(low / df))), stop = std::min(static_cast< int >(a.size( )) - 1, static_cast< int >(std::floor(high / df)));
    if (start > stop) return { 0, "spectrum_arbitration", "采样长度无法覆盖转频搜索范围" };
    int                   bw      = std::max(1, static_cast< int >(std::nearbyint(bandwidth / df / 2)));
    double                minimum = .015 * (2 * bw + 1);
    std::vector< double > prefix(a.size( ) + 1);
    for (std::size_t i = 0; i < a.size( ); ++i) prefix[i + 1] = prefix[i] + a[i];
    auto   index           = [&](double f) { return std::clamp(static_cast< int >(std::floor(f / df + .5)), 0, static_cast< int >(a.size( )) - 1); };
    auto   energy          = [&](int j) { return prefix[std::min(static_cast< int >(a.size( )), j + bw + 1)] - prefix[std::max(0, j - bw)]; };
    auto   penalty         = [&](double f) {double p=0.;for(int d:{2,3,4,5})if(f/d>=low){double e=energy(index(f/d));if(e>minimum*.6)p+=e*(.5/d);}return p; };
    auto   harmonic_energy = [&](double f, int exclude = 0) {double e=0.;for(int h=1;h<=harmonics;++h){if(h==exclude)continue;if(f*h>fs/2)break;e+=energy(index(f*h))/h;}return e; };
    int    best            = -1;
    double best_energy     = 0.;
    for (int j = start; j <= stop; ++j) {
        if (energy(j) < minimum) continue;
        double score = harmonic_energy(j * df) - penalty(j * df);
        if (score > best_energy) {
            best_energy = score;
            best        = j;
        }
    }
    double frequency;
    if (best < 0) {
        best      = static_cast< int >(std::max_element(a.begin( ) + start, a.begin( ) + stop + 1) - a.begin( ));
        frequency = best * df;
    } else
        frequency = parabolic(a, best, df);
    double base_energy = energy(best);
    for (int d : { 5, 4, 3, 2 }) {
        double candidate = frequency / d;
        if (candidate < low) continue;
        int j = index(candidate);
        if (energy(j) < std::max(minimum * .2, base_energy * .12)) continue;
        if (harmonic_energy(candidate, d) > best_energy * .15) {
            frequency = parabolic(a, j, df);
            best      = j;
            break;
        }
    }
    std::vector< SpeedResult > candidates{ { frequency, "spectrum", {} } };
    int                        mid = peak(a, df, 200, std::min(500., fs / 2)), hi = peak(a, df, 100, fs / 4);
    for (auto [j, source] : { std::pair{ mid, "envelope_mesh" }, std::pair{ hi, "envelope_high" } }) {
        if (j < 0) continue;
        auto e = envelope_prepared(y, fs, j * df, low, high, 60, resources);
        if (e.reason.empty( )) {
            e.source = source;
            candidates.push_back(e);
        }
    }
    // Welch: periodic Hann, per-segment constant detrend, 50% overlap. A common
    // positive density scale cannot change the selected peak, so omit it.
    // 段窗取进程级 Hann 表，半谱只填 seg/2+1（与全谱 forward 前半逐位相同）。
    std::size_t                     seg = std::min(y.size( ), static_cast< std::size_t >(std::max(256, static_cast< int >(fs)))), hop = std::max< std::size_t >(1, seg / 2);
    const auto                      window = filtering::hann_table(seg);
    fourier::Plan                   plan(seg);
    std::vector< double >           buffer(seg), power(seg / 2 + 1);
    std::vector< fourier::Complex > transformed(seg / 2 + 1);
    for (std::size_t begin = 0; begin + seg <= y.size( ); begin += hop) {
        double m = core::Map(y.data( ) + begin, seg).mean( );
        for (std::size_t j = 0; j < seg; ++j) buffer[j] = (y[begin + j] - m) * window->values[j];
        plan.forward_half({ buffer.data( ), seg }, { transformed.data( ), transformed.size( ) });
        for (std::size_t j = 0; j < power.size( ); ++j) power[j] += std::norm(transformed[j]);
    }
    int welch = peak(power, fs / seg, low, high);
    if (welch >= 0 && power[welch] > 0) candidates.push_back({ welch * fs / seg, "welch", {} });
    auto ac = autocorrelation_prepared(y, fs, low, high, resources);
    if (ac.reason.empty( )) candidates.push_back(ac);
    std::vector< double > search(a.begin( ) + start, a.begin( ) + stop + 1);
    double                background = median(search);
    auto                  supported  = [&](double f) {int j=index(f);double local=*std::max_element(a.begin()+std::max(0,j-1),a.begin()+std::min(static_cast<int>(a.size()),j+2));return local>std::max(1e-12,5*background); };
    for (const auto &c : candidates) {
        if (c.source.rfind("envelope", 0) != 0 || energy(index(c.frequency)) < minimum * .3) continue;
        int carrier = c.source == "envelope_mesh" ? mid : hi;
        if (carrier < 0) continue;
        double teeth = carrier * df / c.frequency, rounded = std::nearbyint(teeth);
        if (std::abs(teeth - rounded) < .30 && rounded >= 10 && rounded <= 50 && supported(c.frequency)) return c;
    }
    if (ac.reason.empty( )) {
        double ace = energy(index(ac.frequency));
        for (const auto &c : candidates) {
            if (c.frequency <= ac.frequency) continue;
            double ratio = c.frequency / ac.frequency;
            if (ratio >= 1.8 && ratio <= 5.2 && std::abs(ratio - std::nearbyint(ratio)) < .18 && ace > std::max(minimum * .3, energy(index(c.frequency)) * .2) && supported(ac.frequency)) return ac;
        }
    }
    SpeedResult chosen;
    double      score = -std::numeric_limits< double >::infinity( );
    for (const auto &c : candidates) {
        double value = c.frequency < low || c.frequency > high ? -1. : harmonic_energy(c.frequency) - penalty(c.frequency);
        if (c.source == "autocorrelation")
            value *= 1.1;
        else if (c.source == "welch")
            value *= 1.05;
        if (value > score) {
            score  = value;
            chosen = c;
        }
    }
    if (!std::isfinite(chosen.frequency) || chosen.frequency < low || chosen.frequency > high) return { 0, "spectrum_arbitration", "候选仲裁没有产生有效转频" };
    if (!supported(chosen.frequency)) return { 0, "spectrum_arbitration", "搜索范围内没有显著谱峰" };
    return chosen;
}
RidgeResult speed_ridge(std::span< const double > x, double fs, double low, double high, int window, int hop, const RidgeParameters &p) {
    search_range(low, high);
    auto        y = centered(x, fs);
    RidgeResult result;
    if (!std::isfinite(p.peak_to_background) || !std::isfinite(p.local_energy) || !std::isfinite(p.reliable_fraction) || !std::isfinite(p.boundary_fraction) || p.peak_to_background <= 1 || p.local_energy <= 0 || p.reliable_fraction <= 0 || p.reliable_fraction > 1 || p.boundary_fraction < 0 || p.boundary_fraction >= 1 || p.consecutive_boundaries < 0) throw std::invalid_argument("invalid ridge reliability parameters");
    if (window < 64 || window > static_cast< int >(x.size( )) || hop < 1) throw std::invalid_argument("invalid STFT window or hop");
    int frames   = 1 + (static_cast< int >(x.size( )) - window) / hop;
    result.total = frames;
    double df    = fs / window;
    int    start = static_cast< int >(std::ceil(low / df)), stop = std::min(window / 2, static_cast< int >(std::floor(high / df)));
    if (stop - start + 1 < 3 || frames < 3) {
        result.reason = "STFT 搜索频带或时间帧不足";
        return result;
    }
    Workspace w;
    w.prepare(window);
    std::vector< double > a(window / 2 + 1), noise;
    noise.reserve(a.size( ));
    std::vector< double > times, ridge;
    times.reserve(frames);
    ridge.reserve(frames);
    int boundary_count = 0, current_run = 0, longest_run = 0;
    for (int column = 0; column < frames; ++column) {
        for (int j = 0; j < window; ++j) w.real[j] = y[column * hop + j] * w.window[j];
        w.plan.forward({ w.real.data( ), static_cast< std::size_t >(window) }, w.spectrum);
        for (std::size_t j = 0; j < a.size( ); ++j) a[j] = std::sqrt(std::norm(w.spectrum[j])) / (window * .5);
        int    j        = static_cast< int >(std::max_element(a.begin( ) + start, a.begin( ) + stop + 1) - a.begin( ));
        double f        = parabolic(a, j, df);
        auto   power    = [&](int l, int h) {double s=0.;for(int k=std::max(0,l);k<std::min(static_cast<int>(a.size()),h);++k)s+=a[k]*a[k];return s; };
        bool   boundary = j == start || j == stop, outside = f < low - .25 * df || f > high + .25 * df;
        bool   external = j == stop ? power(j + 1, j + 4) > power(j - 2, j + 1) : (j == start && j > 0 ? power(j - 3, j) > power(j + 1, j + 3) : false);
        bool   hit      = boundary && (outside || external);
        boundary_count += hit;
        current_run = hit ? current_run + 1 : 0;
        longest_run = std::max(longest_run, current_run);
        noise.clear( );
        for (int k = 1; k < static_cast< int >(a.size( )); ++k)
            if (k < j - 2 || k > j + 2) noise.push_back(a[k]);
        double background = median(noise) + 1e-15;
        if (a[j] / background < p.peak_to_background || power(j - 2, j + 3) / (power(1, a.size( )) + 1e-30) < p.local_energy) continue;
        if (f >= low && f <= high) {
            times.push_back((column * hop + window * .5) / fs);
            ridge.push_back(f);
        }
    }
    result.reliable = static_cast< int >(times.size( ));
    if (longest_run > p.consecutive_boundaries || boundary_count > static_cast< int >(std::ceil(frames * p.boundary_fraction))) {
        result.reason = "STFT 转频脊线持续触及搜索边界，可能越出搜索范围";
        return result;
    }
    if (times.size( ) < 3 || times.size( ) < static_cast< std::size_t >(std::ceil(frames * p.reliable_fraction))) {
        result.reason = "没有足够可靠的 STFT 转频脊线";
        return result;
    }
    result.frequency.resize(x.size( ));
    core::Array sample_time(x.size( ));
    for (std::size_t i = 0; i < x.size( ); ++i) sample_time[i] = i / fs;
    execution::interpolate(times, ridge, { sample_time.data( ), x.size( ) }, { result.frequency.data( ), x.size( ) });
    int edge                            = std::min< int >(5, times.size( ));
    auto [left_slope, left_intercept]   = sequence::regression(std::span(times).first(edge), std::span(ridge).first(edge));
    auto [right_slope, right_intercept] = sequence::regression(std::span(times).last(edge), std::span(ridge).last(edge));
    int    outside_run = 0, longest_outside = 0;
    bool   internal    = false;
    double first_frame = window * .5 / fs, last_frame = ((frames - 1) * hop + window * .5) / fs;
    for (std::size_t i = 0; i < x.size( ); ++i) {
        double t = sample_time[i];
        if (t < times.front( ))
            result.frequency[i] = left_intercept + left_slope * t;
        else if (t > times.back( ))
            result.frequency[i] = right_intercept + right_slope * t;
        bool out = result.frequency[i] < low || result.frequency[i] > high;
        internal |= out && t >= first_frame && t <= last_frame;
        outside_run         = out ? outside_run + 1 : 0;
        longest_outside     = std::max(longest_outside, outside_run);
        result.frequency[i] = std::clamp(result.frequency[i], low, high);
    }
    if (internal)
        result.reason = "连续转速轨迹在 STFT 记录内部越出搜索范围";
    else if (longest_outside > std::max(1, window / 2))
        result.reason = "连续转速轨迹在边缘长时间越出搜索范围";
    if (!result.reason.empty( )) result.frequency.resize(0);
    return result;
}
}    // namespace cnn_compute::rotation
