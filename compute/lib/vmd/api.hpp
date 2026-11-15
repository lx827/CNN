#pragma once
#include <core/array.hpp>
#include <fourier/api.hpp>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace cnn_compute::vmd {
struct Parameters {
    int           modes          = 5;
    double        alpha          = 2000;
    double        tau            = 0;
    double        tolerance      = 1e-7;
    int           max_iterations = 200;
    bool          dc             = false;
    std::size_t   max_samples    = 51200;    // 0 表示显式处理全长，不补零。
    int           initialization = 1;        // 0 零中心、1 均匀中心、2 对数随机中心。
    std::uint64_t seed           = 0;
};
struct Result {
    // modes 为 [K,valid_length] 行连续；history 为 [max_iterations,K]，
    // 只有前 iterations 行有效。数据独立拥有，不受 Workspace 再执行影响。
    // indeterminate/numerical_failure 的前三个数组为空；residual 保留原有效窗口。
    core::Array modes, center_frequencies_hz, center_frequency_history_hz, residual;
    std::size_t input_length = 0, valid_length = 0;
    int         iterations = 0;
    bool        converged  = false;
    std::string status     = "valid", reason;
};
struct Workspace {
    fourier::Plan fft;
    // ADMM 频域状态按实部/虚部分平面存储：Eigen 3.4 对 complex*double、
    // complex/double 置 PacketAccess=false，交织存储的分量访问又是跨步标量；
    // SoA 使主更新与对偶更新成为纯实数组表达式（SIMD）。分母在表达式内
    // 逐元素求值，无独立缓冲。
    core::Array previous_re, previous_im, current_re, current_im;
    core::Array spectrum_re, spectrum_im, dual_re, dual_im, sum_re, sum_im;
    // FFT 输入输出保持交织复数（pocketfft 契约）。
    std::vector< fourier::Complex > transform;
    core::Array                     mirrored, inverse, frequencies, centers, temporary_centers;
    std::vector< std::size_t >      order;
    // 唯一分配阶段；镜像长度 M=N+2*floor(N/2)，仅存 ceil(M/2) 非负频点。
    // 每活跃调用独占；ADMM 迭代不增长缓冲区，数值失败后仍可复用。
    // FFT 后端的 exec 临时存储按 Fourier Plan 后端契约计算。
    void prepare(std::size_t samples, int modes);
};
void prepare_result(Result &output, std::size_t input_length, const Parameters &parameters);
// 库内接口：已验证的有限一维输入、正采样率/合法参数，输出与输入无重叠。
// output/workspace 已按有效窗口和参数准备；借用同步结束失效；ADMM 不分配。
// 失败清空无效结果数组，复用该 Result 前需重新 prepare_result；Workspace 可直接复用。
void execute(std::span< const double > input, double sample_rate_hz, const Parameters &parameters,
             Result &output, Workspace &workspace);
// 公开入口建立前提，准备拥有型输出与独占工作区；计算公式只在 execute。
Result decompose(std::span< const double > input, double sample_rate_hz, const Parameters &parameters = {});
}    // namespace cnn_compute::vmd
