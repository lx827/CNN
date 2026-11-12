#pragma once

#include <emd/execution.hpp>

namespace cnn_compute::emd {

enum class NoiseMode { single,
                       flip };

struct EnsembleOptions {
    // EEMD 对齐上游可配置的 IMF/包络、max_imfs 和 sift_thresh；
    // sift.energy_thresh 必须为 50，sift.rilling_thresh 必须为空。
    Options   sift;
    int       nensembles     = 4;
    double    ensemble_noise = 0.2;
    NoiseMode noise_mode     = NoiseMode::single;
};

struct CompleteEnsembleOptions {
    Options sift;
    int     nensembles     = 4;
    double  ensemble_noise = 0.2;
};

struct EnsembleWorkspace {
    Workspace sift;
    Array     trial, next, normalized, white_noise, local_mean, previous, accumulator;
    // EEMD 保留各成员以选择模态数；complete ensemble 缓存各噪声的完整分解。
    std::vector< Result > members;
    void                  prepare(std::size_t samples, int nensembles, int pad_width = 2);
};

// normal_noise 是按成员逐行排列的 nensembles * signal.size() 个标准正态值。
// 输入只读借用至同步返回，结果各列拥有独立存储。内部不生成随机数或线程。
// Python 可用 RandomState(seed).standard_normal((nensembles, samples)) 准备噪声。
Result ensemble_sift(std::span< const double > signal, std::span< const double > normal_noise,
                     const EnsembleOptions &options = {});
Result complete_ensemble_sift(std::span< const double >      signal,
                              std::span< const double >      normal_noise,
                              const CompleteEnsembleOptions &options = {});
void   validate(const EnsembleOptions &options);
void   validate(const CompleteEnsembleOptions &options);

namespace execution {
    // 已验证有限输入、参数和噪声形状；输入/噪声不与 workspace 重叠。
    // workspace 由一个活跃调用独占，prepare 后可跨任务复用；所有借用返回时结束。
    // 聚合无单一筛分迭代数，因此 Result.iterations 为空；计算失败状态不伪装成功。
    Result ensemble_sift(std::span< const double > signal, std::span< const double > normal_noise,
                         const EnsembleOptions &options, EnsembleWorkspace &workspace);
    // max_imfs 为真实 IMF 数量上限，最后另外附一列残差；0 表示不限制。
    // 噪声模态不足会抛 out_of_range，与上游越界对应，不补零、不重用其他层。
    Result complete_ensemble_sift(std::span< const double >      signal,
                                  std::span< const double >      normal_noise,
                                  const CompleteEnsembleOptions &options,
                                  EnsembleWorkspace             &workspace);
}    // namespace execution

}    // namespace cnn_compute::emd
