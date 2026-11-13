#pragma once

#include <complex>
#include <cstddef>
#include <memory>
#include <span>
#include <vector>

namespace cnn_compute::fourier {
using Complex = std::complex< double >;

// 同步变换；正变换不归一化，逆变换除以 N，频率按未 fftshift 的顺序。
// 输入输出长度均为 size()，不重叠；借用不逃逸。每个活跃调用独占 Plan 的可写缓冲。
// pocketfft 计划经进程级单槽缓存共享只读：同尺寸重复构造零重建，尺寸变化才重建；
// c2c 与 r2c 计划及各自缓冲按方向惰性准备，纯实/纯复路径不付另一方向的构建与内存。
class Plan {
public:
    explicit Plan(std::size_t samples = 0);
    ~Plan( );
    Plan(Plan &&) noexcept;
    Plan       &operator=(Plan &&) noexcept;
    void        prepare(std::size_t samples);
    std::size_t size( ) const;
    void        forward(std::span< const double > input, std::span< Complex > output);
    // 实输入专用：输出 N/2+1 个非负频点，直接使用缓存的 pocketfft real plan。
    void forward_half(std::span< const double > input, std::span< Complex > output);
    // forward_half 的零填充变体：input 给出有效长度 valid ≤ size()，[valid, size()) 视为零；
    // 直接装填内部缓冲，调用方无需物化零填充临时数组（convolve 场景）。
    void forward_half_padded(const double *input, std::size_t valid, std::span< Complex > output);
    // 仅用于 Hermitian 频谱的 N/2+1 个非负频点；DC/偶数 Nyquist 虚部为零。
    // 任意复谱取实部必须使用 inverse_real，不能用此入口替代。
    // 打包与执行直接发生在调用者输出存储上，不产生额外拷贝。
    void inverse_half(std::span< const Complex > input, std::span< double > output);
    void forward(std::span< const Complex > input, std::span< Complex > output);
    void inverse(std::span< const Complex > input, std::span< Complex > output);
    void inverse_real(std::span< const Complex > input, std::span< double > output);

private:
    struct Impl;
    std::unique_ptr< Impl > impl_;
};

// 公开入口返回独立拥有的数组；长度变化在入口准备 Plan。
std::vector< Complex > fft(std::span< const double > input);
std::vector< Complex > fft(std::span< const Complex > input);
std::vector< Complex > ifft(std::span< const Complex > input);
// 实输入半谱；irfft 需显式给出原长，偶数 Nyquist 与 DC 的虚部按实变换忽略。
std::vector< Complex > rfft(std::span< const double > input);
std::vector< double >  irfft(std::span< const Complex > half_spectrum, std::size_t samples);
std::vector< double >  convolve(std::span< const double > a, std::span< const double > b);
}    // namespace cnn_compute::fourier
