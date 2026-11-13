#pragma once
#include <fourier/api.hpp>
#include <filtering/api.hpp>
#include <core/array.hpp>
#include <complex>
#include <span>
#include <vector>

namespace cnn_compute::diagnostic {
using Complex = std::complex< double >;
struct Workspace {
    fourier::Plan          plan;
    std::vector< double >  window, real, low_power, high_power;
    std::vector< int >     center_bins, upper_bins, lower_bins;
    std::vector< Complex > modulated, first, second, phases, temporary;
    filtering::Workspace   filtering;
    // 每个活跃调用独占；prepare可分配/准备FFT，同规模执行复用。
    // 不保存输入借用，结果和外部输出不受后续复用影响。
    // phases 为信号全长相位表，sc_scoh 按循环频率逐行重建，长度随最大信号增长。
    void prepare(std::size_t samples);
};
struct CyclicResult {
    std::size_t            rows = 0, columns = 0, segments = 0;
    double                 input_scale = 0;
    std::vector< Complex > correlation;
    std::vector< double >  coherence;
};
struct MSBResult {
    std::size_t                  rows = 0, columns = 0, segments = 0;
    std::vector< Complex >       mean;
    std::vector< double >        coherence;
    std::vector< unsigned char > valid;
};
struct BandStatistics {
    double low_hz, high_hz;
    int    level;
    double spectral_kurtosis, impulsiveness, signal_to_background;
};
// 公开结果独立拥有；所有输入连续只读借用至同步返回；不创建线程。
core::Array                   teager(std::span< const double > input);
double                        complex_spectral_kurtosis(std::span< const Complex > input);
std::vector< BandStatistics > filter_bank_kurtogram(std::span< const double > input, double fs,
                                                    int max_level, double min_frequency, int order);
core::Array                   cepstral_prewhiten(std::span< const double > input, double fs,
                                                 std::span< const double > comb, double width = 0.02);
// 直接全局时间复频移，输出行优先(alpha,carrier)，SC保留输入平方/Hz。
// step是窗口步长，segment_length>=32，至少四段；alpha在[0,Nyquist]。
CyclicResult sc_scoh(std::span< const double > input, double fs, std::span< const double > alpha,
                     std::size_t segment_length, std::size_t step);
// 四阶E[X(fc+fm)X(fc-fm)conj(X(fc))²]；先复平均，网格外项为NaN。
MSBResult modulation_bispectrum(std::span< const double > input, double fs,
                                std::span< const double > carriers, std::span< const double > modulation,
                                std::size_t segment_length, std::size_t step, std::size_t minimum_segments);
namespace execution {
    // 形状/参数已验证；output长N，与输入/工作区不重叠，无循环分配。
    void teager(std::span< const double > input, std::span< double > output);
    void cepstral_prewhiten(std::span< const double > input, double fs, std::span< const double > comb,
                            double width, std::span< double > output, Workspace &workspace);
    // 工作区已prepare(segment_length)，输出由入口一次性准备；临时缓冲只随段长增长，
    // 不构造[alpha,segments,FFT]或[segments,FFT]巨型中间数组。
    void sc_scoh(std::span< const double > input, double fs, std::span< const double > alpha,
                 std::size_t segment_length, std::size_t step, CyclicResult &output, Workspace &workspace);
    void modulation_bispectrum(std::span< const double > input, double fs, std::span< const double > carriers,
                               std::span< const double > modulation, std::size_t segment_length,
                               std::size_t step, MSBResult &output, Workspace &workspace);
}    // namespace execution
}    // namespace cnn_compute::diagnostic
