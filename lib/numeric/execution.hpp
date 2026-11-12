#pragma once
#include <fourier/api.hpp>
#include <span>

namespace cnn_compute::numeric::execution {
// 公开入口建立finite/形状前提。调用者准备长度N的周期Hann/windowed缓冲、
// 至少N/2+1的complex缓冲和Plan(N)，amplitude长度N/2+1。
// 所有存储互不重叠；除pocketfft后端exec自身的临时存储外不分配，不留借用。
// 同规模重复执行复用Plan与窗；均值、相干增益和DC/Nyquist规则共用此唯一公式。
void amplitude_spectrum(std::span< const double > input, std::span< double > amplitude,
                        std::span< const double > window, std::span< double > windowed,
                        std::span< fourier::Complex > transformed, fourier::Plan &plan,
                        bool remove_mean = true);
}    // namespace cnn_compute::numeric::execution
