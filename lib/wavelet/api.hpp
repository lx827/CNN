#pragma once

#include <core/array.hpp>
#include <memory>
#include <span>
#include <string>
#include <vector>

namespace cnn_compute::wavelet {

// 不可变滤波器和延拓方式可共享；不依赖 Python，包含 PyWavelets 全部内置离散族。
class Plan {
public:
    explicit Plan(const std::string& wavelet = "db8", const std::string& mode = "symmetric");
    ~Plan();
    Plan(Plan&&) noexcept;
    Plan& operator=(Plan&&) noexcept;
    std::size_t coefficient_size(std::size_t input) const;
    std::size_t reconstruction_size(std::size_t coefficients) const;
    int max_level(std::size_t samples) const;
    // 库内执行入口：借用等长 a/d，输出与输入不重叠。形状由调用者预先建立。
    // a 或 d 可为空，表示该支为零；以下执行不分配、不保存输入 view。
    void analyze(std::span<const double> input, std::span<double> a, std::span<double> d) const;
    void synthesize(std::span<const double> a, std::span<const double> d, std::span<double> output) const;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

struct Coefficients {
    // DWT 顺序 aL,dL,...,d1；WP 为自然路径顺序 aa...,aa...d,...,dd...。
    // bands 独立拥有存储；lengths[0] 为原长，其后为各层系数长。
    std::vector<core::Array> bands;
    std::vector<std::size_t> lengths;
    bool packet = false;
    int level = 0;
};

struct Workspace {
    std::vector<core::Array> nodes;
    core::Array first, second, median;
    // 只在准备阶段分配；同形状执行复用全部节点和重构 scratch。
    void prepare(const Plan& plan, std::size_t samples, int level, bool packet);
};

// 准备独立输出；正层数不超过 max_level，samples>=2。可用于重复执行。
void prepare_coefficients(Coefficients& output, const Plan& plan, std::size_t samples, int level, bool packet);
// 输入借用、输出不重叠；output 和 workspace 已按同一 Plan/形状准备。
// 不分配，失败后 workspace 可重新使用；不修改已经返回的拥有型结果。
void decompose_into(std::span<const double> input, const Plan& plan, Coefficients& output, Workspace& workspace);
void reconstruct_into(const Coefficients& coefficients, const Plan& plan, std::span<double> output, Workspace& workspace);
// 单带/单路径重构，output 长度为原长。无需物化其余分量，工作区已准备。
void reconstruct_component_into(const Coefficients& coefficients, std::size_t component,
                                const Plan& plan, std::span<double> output, Workspace& workspace);

// 公开入口检查数据前提、准备输出和工作区；所有公式复用上述执行路径。
Coefficients decompose(std::span<const double> input, const Plan& plan, int level, bool packet = false);
core::Array reconstruct(const Coefficients& coefficients, const Plan& plan);
// 每个频带单独重构到原时间轴；不复制完整包树，只有返回的波形需要 O(bands*N)。
std::vector<core::Array> reconstruct_components(const Coefficients& coefficients, const Plan& plan);
// 轻量选择重构：只走选定路径，输出为其和；额外波形内存 O(N)，不存全部叶波形。
core::Array reconstruct_selected(const Coefficients& coefficients, const Plan& plan, std::span<const std::size_t> selected);
core::Array denoise(std::span<const double> input, const Plan& plan, int level = 0,
                    const std::string& threshold_mode = "soft", double threshold_scale = 1.0);
}
