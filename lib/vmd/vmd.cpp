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
using Complex = fourier::Complex;
using ComplexArray = Eigen::ArrayXcd;
using ComplexMap = Eigen::Map<ComplexArray>;
using ConstComplexMap = Eigen::Map<const ComplexArray>;
std::size_t valid_size(std::size_t input, const Parameters& p) { return p.max_samples ? std::min(input, p.max_samples) : input; }
void discard_invalid_modes(Result& result) {
    result.modes.resize(0);
    result.center_frequencies_hz.resize(0);
    result.center_frequency_history_hz.resize(0);
}
void validate(std::span<const double> input, double fs, const Parameters& p) {
    if (input.size() < 16 || valid_size(input.size(), p) < 16)
        throw std::invalid_argument("VMD 有效输入必须至少为 16 点");
    if (!std::isfinite(fs) || fs <= 0 || p.modes < 1 || p.max_iterations < 1
        || !std::isfinite(p.alpha) || p.alpha <= 0 || !std::isfinite(p.tau) || p.tau < 0
        || !std::isfinite(p.tolerance) || p.tolerance <= 0 || p.initialization < 0 || p.initialization > 2)
        throw std::invalid_argument("VMD 参数必须有限并在合法范围内");
    for (double value : input) if (!std::isfinite(value)) throw std::invalid_argument("VMD 输入必须有限");
}
}
void Workspace::prepare(std::size_t samples, int modes) {
    const auto length = samples + 2 * (samples / 2);
    const auto bins = (length + 1) / 2;
    fft.prepare(length);
    previous.resize(bins * modes);
    current.resize(bins * modes);
    spectrum.resize(bins);
    dual.resize(bins);
    sum.resize(bins);
    transform.resize(length);
    mirrored.resize(length);
    inverse.resize(length);
    frequencies.resize(bins);
    centers.resize(modes);
    temporary_centers.resize(modes);
    order.resize(modes);
    for (std::size_t k = 0; k < bins; ++k) frequencies[k] = static_cast<double>(k) / length;
}
void prepare_result(Result& result, std::size_t input_length, const Parameters& p) {
    result.input_length = input_length;
    result.valid_length = valid_size(input_length, p);
    result.modes.resize(result.valid_length * p.modes);
    result.residual.resize(result.valid_length);
    result.center_frequencies_hz.resize(p.modes);
    result.center_frequency_history_hz.resize(static_cast<std::size_t>(p.max_iterations) * p.modes);
}
void execute(std::span<const double> input, double fs, const Parameters& p, Result& result, Workspace& ws) {
    const auto n = result.valid_length;
    const auto left = n / 2;
    const auto length = n + 2 * left;
    const auto bins = (length + 1) / 2;
    result.iterations = 0;
    result.converged = false;
    result.status = "valid";
    result.reason.clear();
    const auto segment = Eigen::Map<const core::Array>(input.data(), n);
    result.residual = segment;
    const double scale = segment.abs().maxCoeff();
    const bool constant = scale == 0 || (segment / scale - segment[0] / scale).abs().maxCoeff() == 0;
    if (constant) {
        result.status = "indeterminate";
        result.reason = "zero_variance";
        result.residual = segment;
        discard_invalid_modes(result);
        return;
    }
    ws.mirrored.segment(left, n) = segment / scale;
    for (std::size_t i = 0; i < left; ++i) {
        ws.mirrored[i] = input[left - i - 1] / scale;
        ws.mirrored[left + n + i] = input[n - i - 1] / scale;
    }
    ws.fft.forward({ws.mirrored.data(), length}, ws.transform);
    std::copy_n(ws.transform.begin(), bins, ws.spectrum.begin());
    std::fill(ws.previous.begin(), ws.previous.end(), Complex{});
    std::fill(ws.current.begin(), ws.current.end(), Complex{});
    std::fill(ws.dual.begin(), ws.dual.end(), Complex{});
    std::fill(ws.sum.begin(), ws.sum.end(), Complex{});
    std::mt19937_64 rng(p.seed);
    std::uniform_real_distribution<double> uniform(0.0, 1.0);
    for (int k = 0; k < p.modes; ++k) {
        if (p.initialization == 0) ws.centers[k] = 0;
        else if (p.initialization == 1) ws.centers[k] = 0.5 * k / p.modes;
        else {
            const double low = std::log(1.0 / n);
            ws.centers[k] = std::exp(low + (std::log(0.5) - low) * uniform(rng));
        }
    }
    if (p.initialization == 2) std::sort(ws.centers.data(), ws.centers.data() + p.modes);
    if (p.dc) ws.centers[0] = 0;
    const ConstComplexMap spectrum(ws.spectrum.data(), bins);
    ComplexMap dual(ws.dual.data(), bins), sum(ws.sum.data(), bins);
    for (int iteration = 0; iteration < p.max_iterations; ++iteration) {
        double difference = std::numeric_limits<double>::epsilon();
        for (int k = 0; k < p.modes; ++k) {
            const ConstComplexMap old(ws.previous.data() + static_cast<std::size_t>(k) * bins, bins);
            ComplexMap current(ws.current.data() + static_cast<std::size_t>(k) * bins, bins);
            const Complex* adjacent = k == 0 ? ws.previous.data() + static_cast<std::size_t>(p.modes - 1) * bins
                                            : ws.current.data() + static_cast<std::size_t>(k - 1) * bins;
            sum += ConstComplexMap(adjacent, bins) - old;
            // 分母严格为实数；避免把它提升为 complex 后执行通用复数除法。
            current = (spectrum - sum - dual * 0.5) / (1.0 + p.alpha * (ws.frequencies - ws.centers[k]).square());
            if (k != 0 || !p.dc) {
                const double power = current.abs2().sum();
                if (power > std::numeric_limits<double>::min())
                    ws.centers[k] = (ws.frequencies * current.abs2()).sum() / power;
            }
            difference += (current - old).abs2().sum() / length;
        }
        const ConstComplexMap last(ws.current.data() + static_cast<std::size_t>(p.modes - 1) * bins, bins);
        dual += p.tau * (sum + last - spectrum);
        for (int k = 0; k < p.modes; ++k)
            result.center_frequency_history_hz[static_cast<std::size_t>(iteration) * p.modes + k] = ws.centers[k] * fs;
        ws.previous.swap(ws.current);
        result.iterations = iteration + 1;
        if (!std::isfinite(difference) || !ws.centers.isFinite().all()) {
            result.status = "numerical_failure";
            result.reason = "nonfinite_admm_update";
            discard_invalid_modes(result);
            return;
        }
        if (difference <= p.tolerance) { result.converged = true; break; }
    }
    if (!result.converged) result.reason = "maximum_iterations_reached";
    std::iota(ws.order.begin(), ws.order.end(), std::size_t{0});
    std::sort(ws.order.begin(), ws.order.end(), [&](auto a, auto b) { return ws.centers[a] < ws.centers[b]; });
    result.residual = segment;
    for (int output_mode = 0; output_mode < p.modes; ++output_mode) {
        const auto source_mode = ws.order[output_mode];
        result.center_frequencies_hz[output_mode] = ws.centers[source_mode] * fs;
        std::fill(ws.transform.begin(), ws.transform.end(), Complex{});
        const auto* source = ws.previous.data() + source_mode * bins;
        ws.transform[0] = source[0].real();
        for (std::size_t k = 1; k < bins; ++k) {
            ws.transform[k] = source[k];
            ws.transform[length - k] = std::conj(source[k]);
        }
        ws.fft.inverse_real(ws.transform, {ws.inverse.data(), length});
        Eigen::Map<core::Array> mode(result.modes.data() + static_cast<std::size_t>(output_mode) * n, n);
        mode = ws.inverse.segment(left, n) * scale;
        result.residual -= mode;
    }
    for (int iteration = 0; iteration < result.iterations; ++iteration) {
        auto* row = result.center_frequency_history_hz.data() + static_cast<std::size_t>(iteration) * p.modes;
        for (int k = 0; k < p.modes; ++k) ws.temporary_centers[k] = row[ws.order[k]];
        std::copy_n(ws.temporary_centers.data(), p.modes, row);
    }
}
Result decompose(std::span<const double> input, double fs, const Parameters& p) {
    validate(input, fs, p);
    Result result;
    prepare_result(result, input.size(), p);
    Workspace ws;
    ws.prepare(result.valid_length, p.modes);
    execute(input, fs, p, result, ws);
    return result;
}
}
