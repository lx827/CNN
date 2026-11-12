#include "api.hpp"
#include <sequence/api.hpp>
#include <transforms/hilbert.hpp>
#include <filtering/api.hpp>
#include <numeric/execution.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <numbers>
#include <stdexcept>

namespace cnn_compute::rotation {
namespace {
    constexpr double    pi = std::numbers::pi;
    std::span< double > view(core::Array &a) {
        return { a.data( ), static_cast< std::size_t >(a.size( )) };
    }
    void validate(std::span< const double > x, std::size_t minimum = 1) {
        if (x.size( ) < minimum) throw std::invalid_argument("signal is too short");
        for (double v : x)
            if (!std::isfinite(v)) throw std::invalid_argument("signal must be finite");
    }
    void ordered_axis(std::span< const double > x) {
        validate(x);
        for (std::size_t i = 1; i < x.size( ); ++i)
            if (x[i] <= x[i - 1]) throw std::invalid_argument("axis must increase strictly");
    }
    void axes(std::span< const double > x, std::span< const double > y) {
        ordered_axis(x);
        validate(y);
        if (x.size( ) != y.size( )) throw std::invalid_argument("axes must have equal lengths");
    }
}    // namespace
void Workspace::prepare(std::size_t n) {
    plan.prepare(n);
    real.resize(n);
    spectrum.resize(n);
    temporary.resize(n);
    if (window.size( ) != static_cast< std::ptrdiff_t >(n)) {
        auto h = filtering::hann(n);
        window = core::Map(h.data( ), n);
    }
}
namespace execution {
    void integrate(std::span< const double > t, std::span< const double > speed, std::span< double > phase) {
        phase[0] = 0.;
        for (std::size_t i = 1; i < t.size( ); ++i) phase[i] = phase[i - 1] + (t[i] - t[i - 1]) * (speed[i] + speed[i - 1]) * .5;
    }
    void interpolate(std::span< const double > x, std::span< const double > y, std::span< const double > target, std::span< double > out, bool zero) {
        // 单调目标只走一次输入轴；无临时索引数组。目标乱序用二分查找。
        std::size_t j        = 0;
        double      previous = -std::numeric_limits< double >::infinity( );
        for (std::size_t k = 0; k < target.size( ); ++k) {
            double t = target[k];
            if (t < x.front( )) {
                out[k] = zero ? 0 : y.front( );
                continue;
            }
            if (t > x.back( )) {
                out[k] = zero ? 0 : y.back( );
                continue;
            }
            if (t < previous)
                j = std::upper_bound(x.begin( ), x.end( ), t) - x.begin( ) - 1;
            else
                while (j + 1 < x.size( ) && x[j + 1] <= t) ++j;
            previous = t;
            if (j + 1 == x.size( )) {
                out[k] = y.back( );
                continue;
            }
            out[k] = y[j] + (t - x[j]) / (x[j + 1] - x[j]) * (y[j + 1] - y[j]);
        }
    }
    void amplitude_spectrum(std::span< const double > x, std::span< double > amp, Workspace &w, bool center) {
        numeric::execution::amplitude_spectrum(x, amp, { w.window.data( ), x.size( ) },
                                               { w.real.data( ), x.size( ) }, w.spectrum, w.plan, center);
    }
    void tsa(std::span< const double > x, int spr, std::span< double > cycle, std::span< double > repeated) {
        std::size_t cycles = x.size( ) / spr;
        std::fill(cycle.begin( ), cycle.end( ), 0.);
        for (std::size_t r = 0; r < cycles; ++r)
            for (int j = 0; j < spr; ++j) cycle[j] += x[r * spr + j];
        for (double &v : cycle) v /= cycles;
        for (std::size_t r = 0; r < cycles; ++r) std::copy(cycle.begin( ), cycle.end( ), repeated.begin( ) + r * spr);
    }
}    // namespace execution
core::Array integrate(std::span< const double > t, std::span< const double > speed) {
    axes(t, speed);
    for (double v : speed)
        if (v <= 0) throw std::invalid_argument("speed must be positive");
    core::Array out(t.size( ));
    execution::integrate(t, speed, view(out));
    return out;
}
core::Array interpolate(std::span< const double > x, std::span< const double > y, std::span< const double > target, bool zero) {
    axes(x, y);
    validate(target);
    core::Array out(target.size( ));
    execution::interpolate(x, y, target, view(out), zero);
    return out;
}
core::Array angle_resample(std::span< const double > x, std::span< const double > phase, int spr) {
    axes(phase, x);
    if (spr < 16) throw std::invalid_argument("samples per revolution must be >=16");
    auto count = static_cast< std::ptrdiff_t >(std::floor(phase.back( ) * spr + 1e-9));
    if (count < 16) throw std::invalid_argument("有效转数太少，无法进行等角重采样");
    core::Array target(count), output(count);
    for (std::ptrdiff_t i = 0; i < count; ++i) target[i] = static_cast< double >(i) / spr;
    execution::interpolate(phase, x, { target.data( ), static_cast< std::size_t >(count) }, view(output));
    return output;
}
core::Array amplitude_spectrum(std::span< const double > x, bool center) {
    validate(x, 2);
    Workspace w;
    w.prepare(x.size( ));
    core::Array out(x.size( ) / 2 + 1);
    execution::amplitude_spectrum(x, view(out), w, center);
    return out;
}
core::Array periodic_components(std::span< const double > x, std::span< const double > orders) {
    validate(x, 2);
    Workspace w;
    w.prepare(x.size( ));
    w.plan.forward(x, w.spectrum);
    std::fill(w.temporary.begin( ), w.temporary.end( ), fourier::Complex{});
    for (double order : orders) {
        if (order < 0 || order != std::floor(order) || order > x.size( ) / 2) throw std::invalid_argument("regular 成分超出单转角域奈奎斯特覆盖");
        auto j         = static_cast< std::size_t >(order);
        w.temporary[j] = w.spectrum[j];
        if (j) w.temporary[x.size( ) - j] = w.spectrum[x.size( ) - j];
    }
    core::Array out(x.size( ));
    w.plan.inverse_real(w.temporary, view(out));
    return out;
}
std::pair< core::Array, core::Array > tsa(std::span< const double > x, int spr, int minimum) {
    validate(x);
    if (spr < 1 || minimum < 2 || x.size( ) / spr < static_cast< std::size_t >(minimum)) throw std::invalid_argument("有效完整转数不足，无法形成 TSA");
    core::Array cycle(spr), repeated(x.size( ) / spr * spr);
    execution::tsa(x, spr, view(cycle), view(repeated));
    return { std::move(cycle), std::move(repeated) };
}
TSAComponents tsa_components(std::span< const double > cycle, std::span< const double > mesh_orders, std::span< const double > regular_orders, int revolutions) {
    validate(cycle, 2);
    if (revolutions < 2) throw std::invalid_argument("TSA needs at least two complete revolutions");
    std::size_t spr = cycle.size( ), n = spr * revolutions;
    Workspace   w;
    w.prepare(spr);
    w.plan.forward(cycle, w.spectrum);
    TSAComponents out{ core::Array(n), core::Array(n), core::Array(n), core::Array(n), core::Array(n / 2 + 1) };
    auto          reconstruct = [&](std::span< const double > orders, core::Array &target) {
        std::fill(w.temporary.begin( ), w.temporary.end( ), fourier::Complex{});
        for (double order : orders) {
            if (order < 0 || order != std::floor(order) || order > spr / 2) throw std::invalid_argument("invalid periodic component order");
            auto j         = static_cast< std::size_t >(order);
            w.temporary[j] = w.spectrum[j];
            if (j) w.temporary[spr - j] = w.spectrum[spr - j];
        }
        w.plan.inverse_real(w.temporary, { w.real.data( ), spr });
        for (int r = 0; r < revolutions; ++r) std::copy(w.real.data( ), w.real.data( ) + spr, target.data( ) + r * spr);
    };
    reconstruct(mesh_orders, out.mesh);
    reconstruct(regular_orders, out.regular);
    for (std::size_t j = 0; j < n; ++j) {
        out.residual[j]     = cycle[j % spr] - out.regular[j];
        out.differential[j] = out.regular[j] - out.mesh[j];
    }
    auto coeff = [&](std::ptrdiff_t k) {if(k%revolutions)return fourier::Complex{};
        auto j=(k/revolutions%static_cast<std::ptrdiff_t>(spr)+spr)%spr;
        return j==0?fourier::Complex{}:static_cast<double>(revolutions)*w.spectrum[j]; };
    for (std::ptrdiff_t k = 0; k < out.amplitude.size( ); ++k) {
        auto value       = .5 * coeff(k) - .25 * coeff(k - 1) - .25 * coeff(k + 1);
        out.amplitude[k] = std::abs(value) * 4 / n;
    }
    out.amplitude[0] *= .5;
    if (n % 2 == 0) out.amplitude[out.amplitude.size( ) - 1] *= .5;
    return out;
}
core::Array zoom_spectrum(std::span< const double > x, double fs, double low, double high, int points) {
    validate(x, 64);
    if (!std::isfinite(fs) || !std::isfinite(low) || !std::isfinite(high) || fs <= 0 || low < 0 || high > fs / 2 || high <= low || points < 1) throw std::invalid_argument("invalid Chirp-Z band");
    std::size_t n = x.size( ), m = points, length = 1;
    while (length < n + m - 1) length *= 2;
    std::vector< fourier::Complex > a(length), b(length), fa(length), fb(length);
    double                          step = (high - low) / points, gain = 0.;
    for (std::size_t j = 0; j < n; ++j) {
        double w = .5 - .5 * std::cos(2 * pi * j / n);
        gain += w;
        a[j] = x[j] * w * std::polar(1., -2 * pi * low * j / fs - pi * step * j * j / fs);
    }
    for (std::ptrdiff_t j = -static_cast< std::ptrdiff_t >(n) + 1; j < static_cast< std::ptrdiff_t >(m); ++j)
        b[j + static_cast< std::ptrdiff_t >(n) - 1] = std::polar(1., pi * step * static_cast< double >(j) * j / fs);
    fourier::Plan plan(length);
    plan.forward(a, fa);
    plan.forward(b, fb);
    for (std::size_t j = 0; j < length; ++j) fa[j] *= fb[j];
    plan.inverse(fa, a);
    core::Array out(m);
    for (std::size_t k = 0; k < m; ++k) out[k] = std::abs(a[n - 1 + k]) * 2 / gain;
    if (std::abs(low) <= 1e-8) out[0] *= .5;
    // 高端点不含在网格内；沿既有 isclose 规则，仅命中 Nyquist 时折半。
    if (std::abs(high - fs / 2) <= 1e-8 + 1e-5 * fs / 2 && points % 2 == 0)
        for (int k = 0; k < points; ++k)
            if (std::abs(low + k * step - fs / 2) <= 1e-8 + 1e-5 * fs / 2) out[k] *= .5;
    return out;
}
core::Array real_cepstrum(std::span< const double > x) {
    validate(x, 64);
    Workspace w;
    w.prepare(x.size( ));
    double mean = core::Map(x.data( ), x.size( )).mean( ), maximum = 0.;
    for (std::size_t i = 0; i < x.size( ); ++i) w.real[i] = (x[i] - mean) * (.5 - .5 * std::cos(2 * pi * i / x.size( )));
    w.plan.forward({ w.real.data( ), x.size( ) }, w.spectrum);
    for (auto v : w.spectrum) maximum = std::max(maximum, std::abs(v));
    double floor = std::max(maximum * 1e-12, std::numeric_limits< double >::min( )), logmean = 0.;
    for (std::size_t i = 0; i < x.size( ); ++i) {
        w.real[i] = std::log(std::max(std::abs(w.spectrum[i]), floor));
        logmean += w.real[i];
    }
    logmean /= x.size( );
    for (std::size_t i = 0; i < x.size( ); ++i) w.spectrum[i] = { w.real[i] - logmean, 0. };
    w.plan.inverse_real(w.spectrum, { w.real.data( ), x.size( ) });
    return w.real.head(x.size( ) / 2 + 1).eval( );
}
AMFMResult amfm(std::span< const double > x, double fs) {
    validate(x, 64);
    if (!std::isfinite(fs) || fs <= 0) throw std::invalid_argument("sample_rate_hz must be positive");
    core::Array                  centered = core::Map(x.data( ), x.size( )) - core::Map(x.data( ), x.size( )).mean( );
    transforms::HilbertWorkspace hilbert;
    hilbert.prepare(x.size( ));
    std::vector< fourier::Complex > analytic(x.size( ));
    transforms::execution::analytic_signal({ centered.data( ), x.size( ) }, analytic, hilbert);
    AMFMResult out{ core::Array(x.size( )), core::Array(x.size( ) - 1) };
    double     maximum = 0., minimum = std::numeric_limits< double >::infinity( );
    for (std::size_t i = 0; i < x.size( ); ++i) {
        double a        = std::abs(analytic[i]);
        out.envelope[i] = a;
        maximum         = std::max(maximum, a);
        minimum         = std::min(minimum, a);
    }
    if (maximum == 0 || minimum <= 64 * std::numeric_limits< double >::epsilon( ) * maximum) throw std::invalid_argument("undefined_instantaneous_phase_at_amplitude_null");
    for (std::size_t i = 1; i < x.size( ); ++i) {
        double d = std::arg(analytic[i]) - std::arg(analytic[i - 1]);
        if (d > pi)
            d -= 2 * pi;
        else if (d < -pi)
            d += 2 * pi;
        out.frequency[i - 1] = d * fs / (2 * pi);
    }
    return out;
}
core::Array band_envelope(std::span< const double > x, double fs, double low, double high) {
    validate(x, 32);
    auto                 sos = filtering::butterworth(4, low, high, fs);
    filtering::Workspace filter;
    filter.prepare(x.size( ), sos.size( ));
    core::Array filtered(x.size( ));
    filtering::execution::sosfiltfilt(x, sos, { filtered.data( ), x.size( ) }, filter);
    transforms::HilbertWorkspace hilbert;
    hilbert.prepare(x.size( ));
    std::vector< fourier::Complex > z(x.size( ));
    transforms::execution::analytic_signal({ filtered.data( ), x.size( ) }, z, hilbert);
    core::Array out(x.size( ));
    for (std::size_t j = 0; j < x.size( ); ++j) out[j] = std::abs(z[j]);
    return out;
}
core::Array window_peaks(std::span< const double > axis, std::span< const double > amp, std::span< const double > centers, double width, bool disjoint) {
    axes(axis, amp);
    for (double c : centers)
        if (!std::isfinite(c)) throw std::invalid_argument("window centers must be finite");
    if (!std::isfinite(width) || width < 0) throw std::invalid_argument("window half-width must be finite and not negative");
    core::Array         out(centers.size( ));
    std::vector< bool > occupied(disjoint ? axis.size( ) : 0);
    for (std::size_t k = 0; k < centers.size( ); ++k) {
        auto first = std::lower_bound(axis.begin( ), axis.end( ), centers[k] - width), last = std::upper_bound(axis.begin( ), axis.end( ), centers[k] + width);
        if (first == last) throw std::invalid_argument("阶次窗内没有谱点");
        double maximum = -std::numeric_limits< double >::infinity( );
        for (auto p = first; p != last; ++p) {
            auto j = p - axis.begin( );
            if (disjoint) {
                if (occupied[j]) throw std::invalid_argument("overlapping windows");
                occupied[j] = true;
            }
            maximum = std::max(maximum, amp[j]);
        }
        out[k] = maximum;
    }
    return out;
}
double band_sum(std::span< const double > axis, std::span< const double > values, double center, double width) {
    axes(axis, values);
    if (!std::isfinite(center) || !std::isfinite(width) || width < 0) throw std::invalid_argument("invalid spectrum window");
    double sum = 0.;
    for (std::size_t j = 0; j < axis.size( ); ++j)
        if (std::abs(axis[j] - center) <= width) sum += values[j];
    return sum;
}
LocalPeak local_peak(std::span< const double > axis, std::span< const double > amplitude, double center, double width,
                     double inner, double outer, std::span< const double > exclusions, bool median_background) {
    axes(axis, amplitude);
    for (double c : exclusions)
        if (!std::isfinite(c)) throw std::invalid_argument("window exclusions must be finite");
    if (!std::isfinite(center) || !std::isfinite(width) || !std::isfinite(inner) || !std::isfinite(outer) || width <= 0 || inner < 0 || outer <= inner) throw std::invalid_argument("invalid local spectrum windows");
    LocalPeak             out;
    std::vector< double > background;
    if (median_background) background.reserve(axis.size( ));
    double total = 0.;
    for (std::size_t j = 0; j < axis.size( ); ++j) {
        if (axis[j] <= 0) continue;
        double distance = std::abs(axis[j] - center);
        if (distance <= width && (!out.found || amplitude[j] > out.amplitude)) {
            out.coordinate = axis[j];
            out.amplitude  = amplitude[j];
            out.found      = true;
        }
        if (distance < inner * width || distance > outer * width) continue;
        bool excluded = false;
        for (double other : exclusions)
            if (std::abs(axis[j] - other) <= width) {
                excluded = true;
                break;
            }
        if (excluded) continue;
        ++out.background_count;
        total += amplitude[j];
        if (median_background) background.push_back(amplitude[j]);
    }
    if (out.background_count) {
        if (median_background) {
            auto k = background.size( ) / 2;
            std::nth_element(background.begin( ), background.begin( ) + k, background.end( ));
            out.background = background[k];
            if (background.size( ) % 2 == 0) out.background = (out.background + *std::max_element(background.begin( ), background.begin( ) + k)) * .5;
        } else
            out.background = total / out.background_count;
    }
    return out;
}
CARFeatures car_features(std::span< const double > axis, std::span< const double > amplitude, std::span< const double > targets, double width) {
    axes(axis, amplitude);
    validate(targets);
    if (!std::isfinite(width) || width <= 0) throw std::invalid_argument("CAR half-width must be positive");
    CARFeatures out{ core::Array(targets.size( )), core::Array(targets.size( )), 0, 0 };
    for (std::size_t k = 0; k < targets.size( ); ++k) {
        auto first = std::lower_bound(axis.begin( ), axis.end( ), targets[k] - width), last = std::upper_bound(axis.begin( ), axis.end( ), targets[k] + width);
        if (first == last) throw std::invalid_argument("target_quefrency_not_resolvable");
        auto best = first - axis.begin( );
        for (auto p = first; p != last; ++p) {
            auto j = p - axis.begin( );
            if (std::abs(amplitude[j]) > std::abs(amplitude[best])) best = j;
        }
        out.coordinate[k] = axis[best];
        out.amplitude[k]  = std::abs(amplitude[best]);
    }
    std::vector< double > background;
    for (std::size_t j = 0; j < axis.size( ); ++j) {
        if (axis[j] <= targets.back( ) + width) continue;
        bool excluded = false;
        for (double target : targets)
            if (std::abs(axis[j] - target) <= width) {
                excluded = true;
                break;
            }
        if (!excluded) background.push_back(std::abs(amplitude[j]));
    }
    out.background_count = background.size( );
    if (!background.empty( )) {
        auto k = background.size( ) / 2;
        std::nth_element(background.begin( ), background.begin( ) + k, background.end( ));
        out.background = background[k];
        if (background.size( ) % 2 == 0) out.background = (out.background + *std::max_element(background.begin( ), background.begin( ) + k)) * .5;
    }
    return out;
}
std::pair< double, double > order_statistics(std::span< const double > amp) {
    validate(amp);
    double                sum = 0, energy = 0;
    std::vector< double > top(amp.begin( ), amp.end( ));
    for (double a : amp) {
        if (a < 0) throw std::invalid_argument("spectrum amplitude must not be negative");
        sum += a;
        energy += a * a;
    }
    if (energy <= std::numeric_limits< double >::min( )) return { 0, 0 };
    auto count = std::min< std::size_t >(5, top.size( ));
    std::partial_sort(top.begin( ), top.begin( ) + count, top.end( ), std::greater< double >( ));
    double highest = 0.;
    for (std::size_t j = 0; j < count; ++j) highest += top[j] * top[j];
    double mean = sum / amp.size( ) + std::numeric_limits< double >::min( ), s2 = 0, s4 = 0;
    for (double a : amp) {
        double z = a / mean, sq = z * z;
        s2 += sq;
        s4 += sq * sq;
    }
    s2 /= amp.size( );
    s4 /= amp.size( );
    return { highest / energy, s4 / (s2 * s2 + 1e-12) - 2 };
}
CVSResult cvs(std::span< const double > x, std::span< const double > carrier, std::span< const double > planet, double azimuth, double sensor, double half, int spr) {
    axes(planet, x);
    ordered_axis(carrier);
    if (carrier.size( ) != x.size( )) throw std::invalid_argument("axes must have equal lengths");
    if (x.size( ) < 64 || spr < 64 || spr > 8192 || !std::isfinite(azimuth) || !std::isfinite(sensor) || !std::isfinite(half) || half <= 0) throw std::invalid_argument("invalid CVS angular grid");
    CVSResult                                            result;
    std::vector< std::pair< std::size_t, std::size_t > > pending;
    std::vector< double >                                sums(spr), samples;
    std::vector< std::size_t >                           counts(spr);
    std::size_t                                          filled = 0;
    samples.reserve(x.size( ));
    auto inside = [&](std::size_t j) { return std::abs(std::remainder(carrier[j] + azimuth - sensor, 2 * pi)) <= half; };
    for (std::size_t i = 0; i < x.size( );) {
        if (!inside(i)) {
            ++i;
            continue;
        }
        std::size_t start = i;
        while (i < x.size( ) && inside(i)) ++i;
        std::size_t stop = i;
        if (stop - start < 3) continue;
        long long first = static_cast< long long >(std::ceil(planet[start] * spr / (2 * pi))), last = static_cast< long long >(std::floor(planet[stop - 1] * spr / (2 * pi)));
        if (last < first) continue;
        std::size_t j = start;
        for (long long grid = first; grid <= last; ++grid) {
            double target = grid * (2 * pi / spr);
            while (j + 1 < stop && planet[j + 1] <= target) ++j;
            double v   = j + 1 == stop ? x[j] : x[j] + (target - planet[j]) / (planet[j + 1] - planet[j]) * (x[j + 1] - x[j]);
            int    bin = static_cast< int >((grid % spr + spr) % spr);
            sums[bin] += v;
            if (counts[bin]++ == 0) ++filled;
        }
        pending.emplace_back(start, stop);
        if (filled == static_cast< std::size_t >(spr)) {
            for (int k = 0; k < spr; ++k) samples.push_back(sums[k] / counts[k]);
            result.intervals.insert(result.intervals.end( ), pending.begin( ), pending.end( ));
            pending.clear( );
            ++result.cycles;
            std::fill(sums.begin( ), sums.end( ), 0.);
            std::fill(counts.begin( ), counts.end( ), 0);
            filled = 0;
        }
    }
    result.completed_intervals = result.intervals.size( );
    result.coverage            = static_cast< double >(filled) / spr;
    // 保存未完成覆盖的源窗口供不可判定原因检查；成功包装只返回已用窗口。
    result.intervals.insert(result.intervals.end( ), pending.begin( ), pending.end( ));
    result.signal = core::Map(samples.data( ), samples.size( ));
    return result;
}
}    // namespace cnn_compute::rotation
