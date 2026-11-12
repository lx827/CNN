#pragma once

#include <core/array.hpp>
#include <complex>
#include <memory>
#include <span>
#include <vector>

namespace cnn_compute::transforms {

struct FrequencyResult { core::Array phase, frequency, amplitude; };

std::vector<std::complex<double>> analytic_signal(std::span<const double> signal);
core::Array amplitude_normalise(std::span<const double> signal);

// 对齐 emd 0.8.1 的 Hilbert/NHT 路径：升零相位、零填充中值滤波、
// 一阶 Savitzky-Golay 导数。结果独立拥有存储；平滑窗口为正奇数。
FrequencyResult frequency_transform(std::span<const double> signal, double sample_rate = 1.0,
                                    bool normalised = true, int smooth_phase = 5,
                                    int smooth_frequency = 3);

// FFT 计划与临时复数缓冲区属于调用者；每个活跃调用独占一个工作区。
struct HilbertWorkspace {
    struct Impl;
    std::unique_ptr<Impl> impl;
    HilbertWorkspace();
    ~HilbertWorkspace();
    HilbertWorkspace(HilbertWorkspace&&) noexcept;
    HilbertWorkspace& operator=(HilbertWorkspace&&) noexcept;
    void prepare(std::size_t samples);
};

namespace execution {
// 所有输出与输入、工作区互不重叠且等长；输入和参数在公开边界验证。
// 解析信号复用同一 FFT 结果，不额外创建 Hilbert 虚部数组。
void analytic_signal(std::span<const double> signal, std::span<std::complex<double>> output,
                     HilbertWorkspace& workspace);
void amplitude_normalise(std::span<const double> signal, std::span<double> output,
                         HilbertWorkspace& workspace);
void frequency_transform(std::span<const double> signal, std::span<double> phase,
                         std::span<double> frequency, std::span<double> amplitude,
                         double sample_rate, bool normalised, int smooth_phase,
                         int smooth_frequency, HilbertWorkspace& workspace);
}
} // namespace cnn_compute::transforms
