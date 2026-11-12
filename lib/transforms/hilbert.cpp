// emd 0.8.1 spectra/imftools 路径的 C++ 移植；归属见 lib/LICENSE.emd。
#include <transforms/hilbert.hpp>
#include <envelope/execution.hpp>
#include <fourier/api.hpp>
#include <algorithm>
#include <cmath>
#include <numbers>
#include <stdexcept>
#include <vector>

namespace cnn_compute::transforms {
using core::Array;
namespace {
    constexpr double    pi = std::numbers::pi_v< double >;
    std::span< double > writable(Array &value) {
        return { value.data( ), static_cast< std::size_t >(value.size( )) };
    }
    std::span< const double > readonly(const Array &value) {
        return { value.data( ), static_cast< std::size_t >(value.size( )) };
    }
    void check_signal(std::span< const double > signal) {
        if (signal.empty( )) throw std::invalid_argument("输入不能为空");
        for (double value : signal)
            if (!std::isfinite(value)) throw std::invalid_argument("输入必须有限");
    }
}    // namespace
struct HilbertWorkspace::Impl {
    fourier::Plan                         fft;
    std::vector< std::complex< double > > spectrum, analytic;
    Array                                 normalised, envelope, unwrapped, smoothed;
    std::vector< double >                 median;
    envelope::Workspace                   extrema;
};
HilbertWorkspace::HilbertWorkspace( ) : impl(std::make_unique< Impl >( )) {}
HilbertWorkspace::~HilbertWorkspace( )                                      = default;
HilbertWorkspace::HilbertWorkspace(HilbertWorkspace &&) noexcept            = default;
HilbertWorkspace &HilbertWorkspace::operator=(HilbertWorkspace &&) noexcept = default;
void              HilbertWorkspace::prepare(std::size_t samples) {
    impl->fft.prepare(samples);
    impl->spectrum.resize(samples);
    impl->analytic.resize(samples);
    for (auto *array : { &impl->normalised, &impl->envelope,
                         &impl->unwrapped, &impl->smoothed }) array->resize(samples);
    impl->extrema.prepare(samples, 2);
}
namespace execution {
    void analytic_signal(std::span< const double > signal, std::span< std::complex< double > > output,
                         HilbertWorkspace &workspace) {
        auto      &work = *workspace.impl;
        const auto n    = signal.size( );
        work.fft.forward(signal, work.spectrum);
        // 与 scipy.signal.hilbert 一致：DC 和偶数长度 Nyquist 保留，正频加倍。
        for (std::size_t k = 1; k < (n + 1) / 2; ++k) work.spectrum[k] *= 2.0;
        for (std::size_t k = n / 2 + 1; k < n; ++k) work.spectrum[k] = 0.0;
        work.fft.inverse(work.spectrum, output);
    }
    void amplitude_normalise(std::span< const double > signal, std::span< double > output,
                             HilbertWorkspace &workspace) {
        auto &work = *workspace.impl;
        std::copy(signal.begin( ), signal.end( ), output.begin( ));
        envelope::Options options;
        options.padding       = envelope::Padding::numpypad;
        options.interpolation = interpolation::Method::pchip;
        bool have_envelope    = envelope::execution::combined_envelope(output, writable(work.envelope),
                                                                       options, work.extrema);
        for (int iteration = 0; have_envelope && iteration < 3; ++iteration) {
            for (std::size_t i = 0; i < output.size( ); ++i) output[i] /= work.envelope[i];
            have_envelope = envelope::execution::combined_envelope(output, writable(work.envelope),
                                                                   options, work.extrema);
            if (have_envelope) {
                double sum = 0.0;
                for (double value : work.envelope) sum += value;
                if (std::abs(sum - output.size( )) < 1e-10) break;
            }
        }
    }
    void frequency_transform(std::span< const double > signal, std::span< double > phase,
                             std::span< double > frequency, std::span< double > amplitude,
                             double sample_rate, bool normalised, int smooth_phase,
                             int smooth_frequency, HilbertWorkspace &workspace) {
        auto             &work = *workspace.impl;
        const std::size_t n    = signal.size( );
        if (normalised) {
            amplitude_normalise(signal, writable(work.normalised), workspace);
            analytic_signal(readonly(work.normalised), work.analytic, workspace);
            envelope::Options options;
            if (!envelope::execution::upper_envelope(signal, amplitude, options, work.extrema))
                throw std::runtime_error("NHT 振幅包络极值不足");
        } else {
            analytic_signal(signal, work.analytic, workspace);
            for (std::size_t i = 0; i < n; ++i) amplitude[i] = std::abs(work.analytic[i]);
        }
        double previous_angle = std::arg(work.analytic[0]);
        double correction     = 0.0;
        work.unwrapped[0]     = previous_angle;
        for (std::size_t i = 1; i < n; ++i) {
            const double angle         = std::arg(work.analytic[i]);
            const double delta         = angle - previous_angle;
            double       wrapped_delta = std::fmod(delta + pi, 2.0 * pi);
            if (wrapped_delta < 0.0) wrapped_delta += 2.0 * pi;
            wrapped_delta -= pi;
            if (wrapped_delta == -pi && delta > 0.0) wrapped_delta = pi;
            if (std::abs(delta) >= pi) correction += wrapped_delta - delta;
            work.unwrapped[i] = angle + correction;
            previous_angle    = angle;
        }
        if (smooth_phase > 1) {
            const int half = smooth_phase / 2;
            work.median.resize(smooth_phase);
            for (std::size_t i = 0; i < n; ++i) {
                for (int j = -half; j <= half; ++j) {
                    const auto index      = static_cast< std::ptrdiff_t >(i) + j;
                    work.median[j + half] = index >= 0 && index < static_cast< std::ptrdiff_t >(n)
                                                ? work.unwrapped[index]
                                                : 0.0;
                }
                std::nth_element(work.median.begin( ), work.median.begin( ) + half, work.median.end( ));
                work.smoothed[i] = work.median[half];
            }
        } else
            work.smoothed = work.unwrapped;
        work.smoothed += pi / 2.0;
        // polyorder=1、deriv=1；边界 mode='interp' 为最前/后窗口拟合直线的斜率。
        const int half        = smooth_frequency / 2;
        double    denominator = 0.0;
        for (int j = -half; j <= half; ++j) denominator += double(j) * j;
        for (std::size_t i = 0; i < n; ++i) {
            const std::size_t start      = i < static_cast< std::size_t >(half) ? 0
                                           : i + half >= n                      ? n - smooth_frequency
                                                                                : i - half;
            double            derivative = 0.0;
            for (int j = 0; j < smooth_frequency; ++j)
                derivative += double(j - half) * work.smoothed[start + j];
            frequency[i]   = derivative / denominator / (2.0 * pi) * sample_rate;
            double wrapped = std::fmod(work.smoothed[i], 2.0 * pi);
            if (wrapped < 0.0) wrapped += 2.0 * pi;
            phase[i] = wrapped;
        }
    }
}    // namespace execution
FrequencyResult frequency_transform(std::span< const double > signal, double sample_rate,
                                    bool normalised, int smooth_phase, int smooth_frequency) {
    check_signal(signal);
    if (!std::isfinite(sample_rate) || sample_rate <= 0.0 || smooth_phase < 1
        || smooth_phase % 2 == 0 || smooth_frequency < 3 || smooth_frequency % 2 == 0
        || static_cast< std::size_t >(smooth_frequency) > signal.size( ))
        throw std::invalid_argument("采样率或平滑窗口无效");
    HilbertWorkspace workspace;
    workspace.prepare(signal.size( ));
    FrequencyResult result{ Array(signal.size( )), Array(signal.size( )), Array(signal.size( )) };
    execution::frequency_transform(signal, writable(result.phase), writable(result.frequency),
                                   writable(result.amplitude), sample_rate, normalised,
                                   smooth_phase, smooth_frequency, workspace);
    return result;
}
std::vector< std::complex< double > > analytic_signal(std::span< const double > signal) {
    check_signal(signal);
    HilbertWorkspace workspace;
    workspace.prepare(signal.size( ));
    std::vector< std::complex< double > > result(signal.size( ));
    execution::analytic_signal(signal, result, workspace);
    return result;
}
Array amplitude_normalise(std::span< const double > signal) {
    check_signal(signal);
    HilbertWorkspace workspace;
    workspace.prepare(signal.size( ));
    Array result(signal.size( ));
    execution::amplitude_normalise(signal, writable(result), workspace);
    return result;
}
}    // namespace cnn_compute::transforms
