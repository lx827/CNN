#pragma once

#include <emd/api.hpp>
#include <emd/execution.hpp>
#include <transforms/hilbert.hpp>
#include <stdexcept>

namespace cnn_compute::emd {

enum class FirstMask { zero_crossings, instantaneous_frequency, explicit_frequency };
enum class AmplitudeMode { absolute, ratio_signal, ratio_imf };
class MaskConvergenceFailure : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};
struct MaskOptions {
    IMFOptions imf;
    envelope::Options envelope;
    // 非空时为显式归一化频率；空时按 first_mask 生成 max_imfs 个频率。
    std::vector<double> mask_freqs;
    FirstMask first_mask = FirstMask::zero_crossings;
    double first_frequency = 0.25;
    std::vector<double> mask_amp{1.0};
    AmplitudeMode amp_mode = AmplitudeMode::ratio_signal;
    double mask_step_factor = 2.0;
    int max_imfs = 9;
    int nphases = 4;
    double sift_thresh = 1e-8;
};
struct MaskResult { Result decomposition; core::Array mask_frequencies; };
struct MaskWorkspace {
    Workspace sift;
    transforms::HilbertWorkspace hilbert;
    core::Array mask, perturbed, member, sum, residual, first, phase, frequency, amplitude;
    void prepare(std::size_t samples, int pad_width = 2);
};

// 频率以 cycles/sample 表示；结果不包含额外残差列，与 mask_sift 一致。
NextResult get_next_imf_mask(std::span<const double> signal, double frequency, double amplitude,
                            int nphases = 4, const IMFOptions& options = {},
                            const envelope::Options& envelope_options = {});
double get_mask_frequency(std::span<const double> signal, FirstMask method = FirstMask::zero_crossings,
                          double explicit_frequency = 0.25, const IMFOptions& options = {});
MaskResult mask_sift(std::span<const double> signal, const MaskOptions& options = {});
void validate(const MaskOptions& options);

struct IteratedMaskOptions {
    MaskOptions mask;
    int max_iter = 15;
    int averages = 1;
    double iter_thresh = 0.1;
    double sample_rate = 1.0;
    double weight_power = 2.0;
    bool weighted = true;
    bool exclude_edges = false;
    IteratedMaskOptions();
};
struct IteratedMaskResult {
    MaskResult result;
    core::Array mask_variability;
    int iterations = 0; // 实际执行的 mask 分解次数，含收敛后平均。
    bool converged = false;
};
// 随机初始 mask 由调用者生成后传入 mask.mask_freqs；算法内部不使用全局 RNG。
// 收敛后在线聚合，仅保存当前结果与累加结果，内存不随迭代上限增长。
// 返回频率保留参考语义：收敛平均时为 Hz，迭代上限退出时为 cycles/sample。
IteratedMaskResult iterated_mask_sift(std::span<const double> signal,
                                    const IteratedMaskOptions& options = {});

namespace execution {
// 调用者先 prepare(samples,pad_width)；输入/输出等长且不得与工作区重叠。
// 工作区每个活跃调用独占；跨尺寸或延拓宽度改变后再次 prepare。
// 返回的 MaskResult 拥有独立存储，后续执行不会覆盖它；不保存输入 view。
NextInfo get_next_imf_mask(std::span<const double> signal, std::span<double> output,
                          double frequency, double amplitude, int nphases,
                          const IMFOptions& options, const envelope::Options& envelope_options,
                          MaskWorkspace& workspace);
double get_mask_frequency(std::span<const double> signal, FirstMask method,
                          double explicit_frequency, const IMFOptions& options,
                          MaskWorkspace& workspace);
MaskResult mask_sift(std::span<const double> signal, const MaskOptions& options,
                     MaskWorkspace& workspace);
IteratedMaskResult iterated_mask_sift(std::span<const double> signal,
                                     const IteratedMaskOptions& options, MaskWorkspace& workspace);
}
} // namespace cnn_compute::emd
