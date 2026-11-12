// emd 0.8.1 mask sift 路径的 C++ 移植；归属见 lib/LICENSE.emd。
#include <emd/mask.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <numbers>
#include <stdexcept>

namespace cnn_compute::emd {
namespace {
constexpr double pi = std::numbers::pi_v<double>;
std::span<double> writable(Array& value) { return {value.data(), static_cast<std::size_t>(value.size())}; }
std::span<const double> readonly(const Array& value) { return {value.data(), static_cast<std::size_t>(value.size())}; }
void validate_signal(std::span<const double> signal) {
    if (signal.size() < 3) throw std::invalid_argument("mask 输入至少三个采样点");
    for (double value : signal)
        if (!std::isfinite(value)) throw std::invalid_argument("输入必须有限");
}
bool failure(Status status) { return status == Status::iteration_limit || status == Status::numerical_failure; }
void prepare_frequency(MaskWorkspace& workspace, std::size_t samples) {
    workspace.hilbert.prepare(samples);
    for (auto* array : {&workspace.phase, &workspace.frequency, &workspace.amplitude}) array->resize(samples);
}
}
void MaskWorkspace::prepare(std::size_t samples, int pad_width) {
    sift.prepare(samples, pad_width);
    for (auto* array : {&mask, &perturbed, &member, &sum, &residual, &first}) array->resize(samples);
}
IteratedMaskOptions::IteratedMaskOptions() {
    mask.max_imfs = 6;
    mask.amp_mode = AmplitudeMode::ratio_imf;
}
void validate(const MaskOptions& options) {
    validate(options.imf, options.envelope);
    if (options.max_imfs <= 0 || options.nphases <= 0 || options.mask_amp.empty()
        || !std::isfinite(options.sift_thresh) || options.sift_thresh < 0.0
        || !std::isfinite(options.mask_step_factor) || options.mask_step_factor <= 0.0)
        throw std::invalid_argument("mask 参数无效");
    const auto modes = options.mask_freqs.empty() ? static_cast<std::size_t>(options.max_imfs)
        : std::min<std::size_t>(options.max_imfs, options.mask_freqs.size());
    if (options.mask_amp.size() != 1 && options.mask_amp.size() < modes)
        throw std::invalid_argument("mask 幅值数组短于模态数");
    for (double value : options.mask_amp)
        if (!std::isfinite(value)) throw std::invalid_argument("mask 幅值必须有限");
    for (double value : options.mask_freqs)
        if (!std::isfinite(value)) throw std::invalid_argument("mask 频率必须有限");
    if (options.mask_freqs.empty() && options.first_mask == FirstMask::explicit_frequency
        && (!std::isfinite(options.first_frequency) || options.first_frequency <= 0.0
            || options.first_frequency > 0.5))
        throw std::invalid_argument("首个 mask 频率必须属于 (0, .5]");
}
namespace execution {
NextInfo get_next_imf_mask(std::span<const double> signal, std::span<double> output,
                          double frequency, double amplitude, int nphases,
                          const IMFOptions& options, const envelope::Options& envelope_options,
                          MaskWorkspace& workspace) {
    auto& work = workspace;
    work.sum.setZero();
    NextInfo info;
    info.continue_flag = false;
    const double angular = frequency * 2.0 * pi;
    for (int phase = 0; phase < nphases; ++phase) {
        const double offset = (2.0 * pi / nphases) * phase;
        for (std::size_t i = 0; i < signal.size(); ++i) {
            work.mask[i] = amplitude * std::cos(angular * i + offset);
            work.perturbed[i] = signal[i] + work.mask[i];
        }
        const auto member = execution::get_next_imf(readonly(work.perturbed), writable(work.member),
                                                    options, envelope_options, work.sift);
        info.iterations += member.iterations;
        info.continue_flag = info.continue_flag || member.continue_flag;
        if (failure(member.status)) { info.status = member.status; return info; }
        for (std::size_t i = 0; i < signal.size(); ++i) work.sum[i] += work.member[i] - work.mask[i];
    }
    for (std::size_t i = 0; i < signal.size(); ++i) output[i] = work.sum[i] / nphases;
    info.status = info.continue_flag ? Status::success : Status::insufficient_extrema;
    return info;
}
double get_mask_frequency(std::span<const double> signal, FirstMask method,
                          double explicit_frequency, const IMFOptions& options,
                          MaskWorkspace& workspace) {
    if (method == FirstMask::explicit_frequency) return explicit_frequency;
    // 上游 get_mask_freqs 只接 imf_opts，使用默认包络配置。
    const auto info = execution::get_next_imf(signal, writable(workspace.first), options, {}, workspace.sift);
    if (failure(info.status)) throw MaskConvergenceFailure("首个 IMF 未能完成筛分");
    if (method == FirstMask::zero_crossings) {
        auto sign = [](double value) { return (value > 0.0) - (value < 0.0); };
        std::size_t crossings = 0;
        for (std::size_t i = 1; i < signal.size(); ++i)
            crossings += sign(workspace.first[i]) != sign(workspace.first[i - 1]);
        return double(crossings) / signal.size() / 2.0;
    }
    prepare_frequency(workspace, signal.size());
    transforms::execution::frequency_transform(readonly(workspace.first), writable(workspace.phase),
        writable(workspace.frequency), writable(workspace.amplitude), 1.0, true, 3, 3, workspace.hilbert);
    double weighted_sum = 0.0, weight_sum = 0.0;
    for (std::size_t i = 0; i < signal.size(); ++i) {
        weighted_sum += workspace.frequency[i] * workspace.amplitude[i];
        weight_sum += workspace.amplitude[i];
    }
    if (weight_sum == 0.0) throw std::runtime_error("瞬时频率权重总和为零");
    return weighted_sum / weight_sum;
}
MaskResult mask_sift(std::span<const double> signal, const MaskOptions& options,
                     MaskWorkspace& workspace) {
    auto& work = workspace;
    MaskResult result;
    const int modes = options.mask_freqs.empty() ? options.max_imfs
        : std::min<int>(options.max_imfs, static_cast<int>(options.mask_freqs.size()));
    result.mask_frequencies.resize(options.mask_freqs.empty() ? modes : options.mask_freqs.size());
    if (!options.mask_freqs.empty()) {
        std::copy(options.mask_freqs.begin(), options.mask_freqs.end(), result.mask_frequencies.data());
    } else {
        const double first = execution::get_mask_frequency(signal, options.first_mask,
                                                            options.first_frequency, options.imf, work);
        for (int i = 0; i < modes; ++i)
            result.mask_frequencies[i] = first / std::pow(options.mask_step_factor, i);
    }
    std::copy(signal.begin(), signal.end(), work.residual.data());
    double scale = options.amp_mode == AmplitudeMode::absolute ? 1.0 : execution::standard_deviation(signal);
    for (int mode = 0; mode < modes; ++mode) {
        if (mode && options.amp_mode == AmplitudeMode::ratio_imf)
            scale = execution::standard_deviation(readonly(result.decomposition.components.back()));
        const double amplitude = options.mask_amp[options.mask_amp.size() == 1 ? 0 : mode] * scale;
        Array output(signal.size());
        const auto info = execution::get_next_imf_mask(readonly(work.residual), writable(output),
            result.mask_frequencies[mode], amplitude, options.nphases, options.imf, options.envelope, work);
        result.decomposition.iterations.push_back(info.iterations);
        if (failure(info.status)) { result.decomposition.status = info.status; break; }
        result.decomposition.components.push_back(std::move(output));
        // 递推剩余信号，不为模仿参考归约次序重复扫描全部历史模态。
        work.residual -= result.decomposition.components.back();
        if (!info.continue_flag) { result.decomposition.status = Status::insufficient_extrema; break; }
        double absolute_sum = 0.0;
        for (double value : result.decomposition.components.back()) absolute_sum += std::abs(value);
        if (absolute_sum < options.sift_thresh) break;
    }
    return result;
}
IteratedMaskResult iterated_mask_sift(std::span<const double> signal,
                                     const IteratedMaskOptions& options, MaskWorkspace& workspace) {
    const auto n = signal.size();
    auto mask_options = options.mask;
    const int modes = mask_options.mask_freqs.empty() ? mask_options.max_imfs
        : std::min<int>(mask_options.max_imfs, mask_options.mask_freqs.size());
    mask_options.max_imfs = modes;
    std::vector<double> mask = mask_options.mask_freqs;
    if (mask.empty()) {
        // 初始化只需要频率，不执行随后丢弃的完整 mask 分解。
        const double first = execution::get_mask_frequency(signal, mask_options.first_mask,
            mask_options.first_frequency, mask_options.imf, workspace);
        mask.resize(modes);
        for (int i = 0; i < modes; ++i) mask[i] = first / std::pow(mask_options.mask_step_factor, i);
    }
    prepare_frequency(workspace, n);
    int iteration = 0, averages_done = 0;
    bool converged = false;
    Array variance;
    Array mean_mask, mask_m2;
    IteratedMaskResult result;
    while (true) {
        const auto previous = mask;
        mask_options.mask_freqs = mask;
        auto current = execution::mask_sift(signal, mask_options, workspace);
        if (failure(current.decomposition.status)) {
            return {std::move(current), std::move(variance), iteration + averages_done + 1, false};
        }
        const auto found = current.decomposition.components.size();
        mask.resize(found);
        const auto edge = options.exclude_edges ? static_cast<std::size_t>(0.025 * n) : 0;
        for (std::size_t mode = 0; mode < found; ++mode) {
            transforms::execution::frequency_transform(readonly(current.decomposition.components[mode]),
                writable(workspace.phase), writable(workspace.frequency), writable(workspace.amplitude),
                options.sample_rate, true, 5, 3, workspace.hilbert);
            double numerator = 0.0, denominator = 0.0;
            for (std::size_t i = edge; i < n - edge; ++i) {
                const double weight = options.weighted ? std::pow(workspace.amplitude[i], options.weight_power) : 1.0;
                numerator += workspace.frequency[i] * weight;
                denominator += weight;
            }
            if (denominator == 0.0) throw std::runtime_error("迭代 mask 的频率权重总和为零");
            mask[mode] = numerator / denominator / options.sample_rate;
        }
        variance.resize(std::min(mask.size(), previous.size()));
        bool stable = true;
        for (Eigen::Index i = 0; i < variance.size(); ++i) {
            variance[i] = std::abs((mask[i] - previous[i]) / previous[i]);
            if (!std::isnan(variance[i]) && !(variance[i] < options.iter_thresh)) stable = false;
        }
        if (stable || converged) {
            converged = true;
            if (averages_done == 0) {
                result.result.decomposition = std::move(current.decomposition);
                mean_mask.resize(found);
                mask_m2 = Array::Zero(found);
                std::copy_n(previous.begin(), found, mean_mask.data());
            } else {
                // 仅聚合共同有效模态，不为上游的历史零填充缺陷保留大数组。
                const auto count = std::min(result.result.decomposition.components.size(), found);
                result.result.decomposition.components.resize(count);
                result.result.decomposition.iterations.resize(count);
                mean_mask.conservativeResize(count); mask_m2.conservativeResize(count);
                for (std::size_t mode = 0; mode < count; ++mode) {
                    result.result.decomposition.components[mode] += current.decomposition.components[mode];
                    result.result.decomposition.iterations[mode] += current.decomposition.iterations[mode];
                    const double delta = previous[mode] - mean_mask[mode];
                    mean_mask[mode] += delta / (averages_done + 1);
                    mask_m2[mode] += delta * (previous[mode] - mean_mask[mode]);
                }
            }
            if (++averages_done == options.averages) {
                for (auto& component : result.result.decomposition.components) component /= averages_done;
                result.result.mask_frequencies = mean_mask * options.sample_rate;
                result.mask_variability = options.averages == 1 ? variance
                    : Array((mask_m2 / averages_done).sqrt() * options.sample_rate);
                result.iterations = iteration + averages_done;
                result.converged = true;
                return result;
            }
        } else if (++iteration >= options.max_iter) {
            current.mask_frequencies.resize(mask.size());
            std::copy(mask.begin(), mask.end(), current.mask_frequencies.data());
            current.decomposition.status = Status::iteration_limit;
            return {std::move(current), std::move(variance), iteration, false};
        }
    }
}
}
NextResult get_next_imf_mask(std::span<const double> signal, double frequency, double amplitude,
                            int nphases, const IMFOptions& options,
                            const envelope::Options& envelope_options) {
    validate_signal(signal); validate(options, envelope_options);
    if (!std::isfinite(frequency) || !std::isfinite(amplitude) || nphases <= 0)
        throw std::invalid_argument("mask 参数无效");
    MaskWorkspace workspace; workspace.prepare(signal.size(), envelope_options.pad_width);
    NextResult result{Array(signal.size()), {}};
    result.info = execution::get_next_imf_mask(signal, writable(result.imf), frequency, amplitude,
                                              nphases, options, envelope_options, workspace);
    return result;
}
double get_mask_frequency(std::span<const double> signal, FirstMask method,
                          double explicit_frequency, const IMFOptions& options) {
    validate_signal(signal); validate(options, {});
    if (method == FirstMask::explicit_frequency && (!std::isfinite(explicit_frequency)
        || explicit_frequency <= 0.0 || explicit_frequency > 0.5))
        throw std::invalid_argument("首个 mask 频率必须属于 (0, .5]");
    MaskWorkspace workspace; workspace.prepare(signal.size());
    return execution::get_mask_frequency(signal, method, explicit_frequency, options, workspace);
}
MaskResult mask_sift(std::span<const double> signal, const MaskOptions& options) {
    validate_signal(signal); validate(options);
    MaskWorkspace workspace; workspace.prepare(signal.size(), options.envelope.pad_width);
    return execution::mask_sift(signal, options, workspace);
}
IteratedMaskResult iterated_mask_sift(std::span<const double> signal,
                                    const IteratedMaskOptions& options) {
    validate_signal(signal); validate(options.mask);
    if (signal.size() < 5 || options.max_iter <= 0 || options.averages <= 0
        || options.mask.mask_freqs.size() > static_cast<std::size_t>(options.mask.max_imfs)
        || !std::isfinite(options.iter_thresh) || options.iter_thresh < 0.0
        || !std::isfinite(options.sample_rate) || options.sample_rate <= 0.0
        || !std::isfinite(options.weight_power)) throw std::invalid_argument("迭代 mask 参数无效");
    MaskWorkspace workspace; workspace.prepare(signal.size(), options.mask.envelope.pad_width);
    return execution::iterated_mask_sift(signal, options, workspace);
}
} // namespace cnn_compute::emd
