#pragma once
#include <core/array.hpp>
#include <fourier/api.hpp>
#include <array>
#include <span>
#include <vector>

namespace cnn_compute::numeric {
using Matrix     = Eigen::Matrix< double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor >;
using Statistics = std::array< double, 8 >;    // peak,rms,Pearson kurtosis,skewness,margin,shape,impulse,crest
struct Spectrum {
    core::Array frequency, amplitude, power;
};
struct Stft {
    core::Array time, frequency;
    Matrix      amplitude;
};
struct TimeDomain {
    Statistics  overall;
    core::Array time;
    Matrix      values;
    int         window, step;
};
// 输入只读借用至返回；全部结果独立拥有。入口验证参数，热循环不重复扫描。
Spectrum    spectrum(std::span< const double > signal, double fs, bool remove_mean = true);
Stft        stft(std::span< const double > signal, double fs, int window, int overlap, int nfft);
core::Array cepstrum(std::span< const double > signal);
core::Array hilbert_envelope(std::span< const double > signal);
Statistics  statistics(std::span< const double > signal, double margin_floor = 1e-12);
TimeDomain  time_domain(std::span< const double > signal, double fs, int window = 1024, int step = 0);
Matrix      segmented_rms(std::span< const double > signal, double fs, std::size_t segment, bool remove_mean = true);
Matrix      extrema(std::span< const double > x, std::span< const double > y, std::size_t maximum);
core::Array autocorrelation(std::span< const double > signal, bool demean = true);
}    // namespace cnn_compute::numeric
