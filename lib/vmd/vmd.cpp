// ADMM 公式参照 Dragomiretskiy & Zosso (2014) 和 vrcarva/vmdpy 官方实现。
// MIT 归属见 ../LICENSE.vmdpy；本实现使用两轮、单边、模态连续存储。
#include "api.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <random>
#include <stdexcept>

namespace cnn_compute::vmd {
namespace {
    using Complex      = fourier::Complex;
    using RealMap      = Eigen::Map< core::Array >;
    using ConstRealMap = Eigen::Map< const core::Array >;
    std::size_t valid_size(std::size_t input, const Parameters &p) {
        return p.max_samples ? std::min(input, p.max_samples) : input;
    }
    void discard_invalid_modes(Result &result) {
        result.modes.resize(0);
        result.center_frequencies_hz.resize(0);
        result.center_frequency_history_hz.resize(0);
    }
    void validate(std::span< const double > input, double fs, const Parameters &p) {
        if (input.size( ) < 16 || valid_size(input.size( ), p) < 16)
            throw std::invalid_argument("VMD 有效输入必须至少为 16 点");
        if (!std::isfinite(fs) || fs <= 0 || p.modes < 1 || p.max_iterations < 1
            || !std::isfinite(p.alpha) || p.alpha <= 0 || !std::isfinite(p.tau) || p.tau < 0
            || !std::isfinite(p.tolerance) || p.tolerance <= 0 || p.initialization < 0 || p.initialization > 2)
            throw std::invalid_argument("VMD 参数必须有限并在合法范围内");
        for (double value : input)
            if (!std::isfinite(value)) throw std::invalid_argument("VMD 输入必须有限");
    }
}    // namespace
void Workspace::prepare(std::size_t samples, int modes) {
    const auto length = samples + 2 * (samples / 2);
    const auto bins   = (length + 1) / 2;
    fft.prepare(length);
    previous_re.resize(bins * modes);
    previous_im.resize(bins * modes);
    current_re.resize(bins * modes);
    current_im.resize(bins * modes);
    spectrum_re.resize(bins);
    spectrum_im.resize(bins);
    dual_re.resize(bins);
    dual_im.resize(bins);
    sum_re.resize(bins);
    sum_im.resize(bins);
    transform.resize(length);
    mirrored.resize(length);
    inverse.resize(length);
    frequencies.resize(bins);
    centers.resize(modes);
    temporary_centers.resize(modes);
    order.resize(modes);
    for (std::size_t k = 0; k < bins; ++k) frequencies[k] = static_cast< double >(k) / length;
}
void prepare_result(Result &result, std::size_t input_length, const Parameters &p) {
    result.input_length = input_length;
    result.valid_length = valid_size(input_length, p);
    result.modes.resize(result.valid_length * p.modes);
    result.residual.resize(result.valid_length);
    result.center_frequencies_hz.resize(p.modes);
    result.center_frequency_history_hz.resize(static_cast< std::size_t >(p.max_iterations) * p.modes);
}
void execute(std::span< const double > input, double fs, const Parameters &p, Result &result, Workspace &ws) {
    const auto n      = result.valid_length;
    const auto left   = n / 2;
    const auto length = n + 2 * left;
    const auto bins   = (length + 1) / 2;
    result.iterations = 0;
    result.converged  = false;
    result.status     = "valid";
    result.reason.clear( );
    const auto segment    = Eigen::Map< const core::Array >(input.data( ), n);
    result.residual       = segment;
    const double scale    = segment.abs( ).maxCoeff( );
    const bool   constant = scale == 0 || (segment / scale - segment[0] / scale).abs( ).maxCoeff( ) == 0;
    if (constant) {
        result.status   = "indeterminate";
        result.reason   = "zero_variance";
        result.residual = segment;
        discard_invalid_modes(result);
        return;
    }
    ws.mirrored.segment(left, n) = segment / scale;
    for (std::size_t i = 0; i < left; ++i) {
        ws.mirrored[i]            = input[left - i - 1] / scale;
        ws.mirrored[left + n + i] = input[n - i - 1] / scale;
    }
    ws.fft.forward({ ws.mirrored.data( ), length }, ws.transform);
    for (std::size_t k = 0; k < bins; ++k) {
        ws.spectrum_re[k] = ws.transform[k].real( );
        ws.spectrum_im[k] = ws.transform[k].imag( );
    }
    ws.previous_re.setZero( );
    ws.previous_im.setZero( );
    ws.current_re.setZero( );
    ws.current_im.setZero( );
    ws.dual_re.setZero( );
    ws.dual_im.setZero( );
    ws.sum_re.setZero( );
    ws.sum_im.setZero( );
    std::mt19937_64                          rng(p.seed);
    std::uniform_real_distribution< double > uniform(0.0, 1.0);
    for (int k = 0; k < p.modes; ++k) {
        if (p.initialization == 0)
            ws.centers[k] = 0;
        else if (p.initialization == 1)
            ws.centers[k] = 0.5 * k / p.modes;
        else {
            const double low = std::log(1.0 / n);
            ws.centers[k]    = std::exp(low + (std::log(0.5) - low) * uniform(rng));
        }
    }
    if (p.initialization == 2) std::sort(ws.centers.data( ), ws.centers.data( ) + p.modes);
    if (p.dc) ws.centers[0] = 0;
    const ConstRealMap spectrum_re(ws.spectrum_re.data( ), bins), spectrum_im(ws.spectrum_im.data( ), bins);
    RealMap            sum_re(ws.sum_re.data( ), bins), sum_im(ws.sum_im.data( ), bins);
    for (int iteration = 0; iteration < p.max_iterations; ++iteration) {
        double difference = std::numeric_limits< double >::epsilon( );
        for (int k = 0; k < p.modes; ++k) {
            const auto    base = static_cast< std::size_t >(k) * bins;
            ConstRealMap  old_re(ws.previous_re.data( ) + base, bins), old_im(ws.previous_im.data( ) + base, bins);
            RealMap       current_re(ws.current_re.data( ) + base, bins), current_im(ws.current_im.data( ) + base, bins);
            const double *adjacent_re = k == 0
                                            ? ws.previous_re.data( ) + static_cast< std::size_t >(p.modes - 1) * bins
                                            : ws.current_re.data( ) + static_cast< std::size_t >(k - 1) * bins;
            const double *adjacent_im = k == 0
                                            ? ws.previous_im.data( ) + static_cast< std::size_t >(p.modes - 1) * bins
                                            : ws.current_im.data( ) + static_cast< std::size_t >(k - 1) * bins;
            // Σû 增量维护：分量加减与复数逐元素同值同序。
            sum_re += ConstRealMap(adjacent_re, bins) - old_re;
            sum_im += ConstRealMap(adjacent_im, bins) - old_im;
            // 主更新写成纯实数组表达式：operator/(complex,T) 即 complex(re/rhs,
            // im/rhs)，实/实商走 packet 除法；分母在表达式内逐元素求值，
            // 不物化——每模态一趟物化要额外读写两个 bins 平面的流量。
            const auto denominator = 1.0 + p.alpha * (ws.frequencies - ws.centers[k]).square( );
            if (p.tau == 0) {
                // dual 恒为 +0.0，x-(+0.0)≡x（含 -0.0），直接省去该项。
                current_re = (spectrum_re - sum_re) / denominator;
                current_im = (spectrum_im - sum_im) / denominator;
            } else {
                current_re = (spectrum_re - sum_re - ws.dual_re * 0.5) / denominator;
                current_im = (spectrum_im - sum_im - ws.dual_im * 0.5) / denominator;
            }
            // 三个归约保持逐元素 (re*re+im*im) 的顺序标量累加：Eigen 复数 abs2
            // 无 packet，原实现即顺序链；改归约树会变末位并可能翻转收敛轮数。
            if (k != 0 || !p.dc) {
                double power = 0;
                for (std::size_t t = 0; t < bins; ++t)
                    power += current_re[t] * current_re[t] + current_im[t] * current_im[t];
                if (power > std::numeric_limits< double >::min( )) {
                    double moment = 0;
                    for (std::size_t t = 0; t < bins; ++t)
                        moment += ws.frequencies[t]
                                  * (current_re[t] * current_re[t] + current_im[t] * current_im[t]);
                    ws.centers[k] = moment / power;
                }
            }
            double drift = 0;
            for (std::size_t t = 0; t < bins; ++t) {
                const double gap_re = current_re[t] - old_re[t], gap_im = current_im[t] - old_im[t];
                drift += gap_re * gap_re + gap_im * gap_im;
            }
            difference += drift / length;
        }
        // tau==0（Python 默认）时 dual 全程 +0.0，整趟对偶更新跳过。
        if (p.tau != 0) {
            const auto   tail = static_cast< std::size_t >(p.modes - 1) * bins;
            ConstRealMap last_re(ws.current_re.data( ) + tail, bins), last_im(ws.current_im.data( ) + tail, bins);
            RealMap      dual_re(ws.dual_re.data( ), bins), dual_im(ws.dual_im.data( ), bins);
            dual_re += p.tau * (sum_re + last_re - spectrum_re);
            dual_im += p.tau * (sum_im + last_im - spectrum_im);
        }
        for (int k = 0; k < p.modes; ++k)
            result.center_frequency_history_hz[static_cast< std::size_t >(iteration) * p.modes + k] = ws.centers[k] * fs;
        ws.previous_re.swap(ws.current_re);
        ws.previous_im.swap(ws.current_im);
        result.iterations = iteration + 1;
        if (!std::isfinite(difference) || !ws.centers.isFinite( ).all( )) {
            result.status = "numerical_failure";
            result.reason = "nonfinite_admm_update";
            discard_invalid_modes(result);
            return;
        }
        if (difference <= p.tolerance) {
            result.converged = true;
            break;
        }
    }
    if (!result.converged) result.reason = "maximum_iterations_reached";
    std::iota(ws.order.begin( ), ws.order.end( ), std::size_t{ 0 });
    std::sort(ws.order.begin( ), ws.order.end( ), [&](auto a, auto b) { return ws.centers[a] < ws.centers[b]; });
    result.residual = segment;
    for (int output_mode = 0; output_mode < p.modes; ++output_mode) {
        const auto source_mode                    = ws.order[output_mode];
        result.center_frequencies_hz[output_mode] = ws.centers[source_mode] * fs;
        std::fill(ws.transform.begin( ), ws.transform.end( ), Complex{});
        const double *source_re = ws.previous_re.data( ) + source_mode * bins;
        const double *source_im = ws.previous_im.data( ) + source_mode * bins;
        ws.transform[0]         = source_re[0];
        for (std::size_t k = 1; k < bins; ++k) {
            ws.transform[k]          = Complex(source_re[k], source_im[k]);
            ws.transform[length - k] = Complex(source_re[k], -source_im[k]);
        }
        ws.fft.inverse_real(ws.transform, { ws.inverse.data( ), length });
        Eigen::Map< core::Array > mode(result.modes.data( ) + static_cast< std::size_t >(output_mode) * n, n);
        mode = ws.inverse.segment(left, n) * scale;
        result.residual -= mode;
    }
    for (int iteration = 0; iteration < result.iterations; ++iteration) {
        auto *row = result.center_frequency_history_hz.data( ) + static_cast< std::size_t >(iteration) * p.modes;
        for (int k = 0; k < p.modes; ++k) ws.temporary_centers[k] = row[ws.order[k]];
        std::copy_n(ws.temporary_centers.data( ), p.modes, row);
    }
}
Result decompose(std::span< const double > input, double fs, const Parameters &p) {
    validate(input, fs, p);
    Result result;
    prepare_result(result, input.size( ), p);
    Workspace ws;
    ws.prepare(result.valid_length, p.modes);
    execute(input, fs, p, result, ws);
    return result;
}
}    // namespace cnn_compute::vmd
