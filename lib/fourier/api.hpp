#pragma once

#include <complex>
#include <cstddef>
#include <memory>
#include <span>
#include <vector>

namespace cnn_compute::fourier {
using Complex = std::complex< double >;

// 同步变换；正变换不归一化，逆变换除以 N，频率按未 fftshift 的顺序。
// 输入输出长度均为 size()，不重叠；借用不逃逸。每个活跃调用独占 Plan。
// prepare 可分配 FFT 后端缓存；同规模执行复用缓存和实数适配缓冲区。
class Plan {
public:
    explicit Plan(std::size_t samples = 0);
    ~Plan( );
    Plan(Plan &&) noexcept;
    Plan       &operator=(Plan &&) noexcept;
    void        prepare(std::size_t samples);
    std::size_t size( ) const;
    void        forward(std::span< const double > input, std::span< Complex > output);
    void        forward(std::span< const Complex > input, std::span< Complex > output);
    void        inverse(std::span< const Complex > input, std::span< Complex > output);
    void        inverse_real(std::span< const Complex > input, std::span< double > output);

private:
    struct Impl;
    std::unique_ptr< Impl > impl_;
};

// 公开入口返回独立拥有的数组；长度变化在入口准备 Plan。
std::vector< Complex > fft(std::span< const double > input);
std::vector< Complex > fft(std::span< const Complex > input);
std::vector< Complex > ifft(std::span< const Complex > input);
std::vector< double >  convolve(std::span< const double > a, std::span< const double > b);
}    // namespace cnn_compute::fourier
