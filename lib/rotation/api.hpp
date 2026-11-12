#pragma once
#include <core/array.hpp>
#include <fourier/api.hpp>
#include <span>
#include <string>
#include <utility>
#include <vector>

namespace cnn_compute::rotation {
// 输入同步只读借用，不逃逸；公开结果独立拥有存储。每次活跃调用独占工作区。
// prepare 是可能分配阶段，同长度重复执行不重建 FFT plan；输出不可与输入重叠。
struct Workspace {
    fourier::Plan                   plan;
    core::Array                     real, window;
    std::vector< fourier::Complex > spectrum, temporary;
    void                            prepare(std::size_t n);
};
namespace execution {
    void integrate(std::span< const double > time, std::span< const double > speed, std::span< double > phase);
    void interpolate(std::span< const double > x, std::span< const double > y,
                     std::span< const double > target, std::span< double > output, bool zero_outside = false);
    void amplitude_spectrum(std::span< const double > x, std::span< double > amplitude, Workspace &workspace, bool center = true);
    void tsa(std::span< const double > x, int samples_per_revolution, std::span< double > cycle, std::span< double > repeated);
}    // namespace execution
core::Array integrate(std::span< const double > time, std::span< const double > speed);
core::Array interpolate(std::span< const double > x, std::span< const double > y, std::span< const double > target, bool zero_outside = false);
core::Array angle_resample(std::span< const double > signal, std::span< const double > phase, int samples_per_revolution);
core::Array amplitude_spectrum(std::span< const double > x, bool center = true);
core::Array periodic_components(std::span< const double > cycle, std::span< const double > orders);
struct TSAComponents {
    core::Array mesh, regular, residual, differential, amplitude;
};
// 共享一次单圈DFT；整圈平铺的Hann谱由DFT移频恒等式构造，不重做长记录FFT。
TSAComponents                         tsa_components(std::span< const double > cycle, std::span< const double > mesh_orders,
                                                     std::span< const double > regular_orders, int revolutions);
std::pair< core::Array, core::Array > tsa(std::span< const double > x, int samples_per_revolution, int minimum_revolutions);
core::Array                           zoom_spectrum(std::span< const double > x, double sample_rate, double low, double high, int points);
core::Array                           real_cepstrum(std::span< const double > x);
struct AMFMResult {
    core::Array envelope, frequency;
};
AMFMResult  amfm(std::span< const double > x, double sample_rate);
core::Array band_envelope(std::span< const double > x, double fs, double low, double high);
// 局部谱窗口统一计算。窗口顺序决定返回顺序；不可解析/相交以异常报告，调用方映射领域状态。
core::Array window_peaks(std::span< const double > axis, std::span< const double > amplitude,
                         std::span< const double > centers, double half_width, bool disjoint = false);
double      band_sum(std::span< const double > axis, std::span< const double > values, double center, double half_width);
struct LocalPeak {
    double      coordinate = 0, amplitude = 0, background = 0;
    std::size_t background_count = 0;
    bool        found            = false;
};
LocalPeak local_peak(std::span< const double > axis, std::span< const double > amplitude,
                     double center, double half_width, double background_inner, double background_outer,
                     std::span< const double > exclusions, bool median_background);
struct CARFeatures {
    core::Array coordinate, amplitude;
    double      background;
    std::size_t background_count;
};
CARFeatures                 car_features(std::span< const double > axis, std::span< const double > cepstrum,
                                         std::span< const double > targets, double half_width);
std::pair< double, double > order_statistics(std::span< const double > amplitude);
struct RidgeParameters {
    double peak_to_background = 8, local_energy = .12, reliable_fraction = .6, boundary_fraction = .2;
    int    consecutive_boundaries = 2;
};
struct RidgeResult {
    core::Array frequency;
    int         reliable = 0, total = 0;
    std::string reason;
};
RidgeResult speed_ridge(std::span< const double > x, double fs, double low, double high, int window, int hop, const RidgeParameters &parameters);
struct SpeedResult {
    double      frequency = 0;
    std::string source, reason;
};
SpeedResult spectrum_speed(std::span< const double > x, double fs, double low, double high, int harmonics, double bandwidth, double smoothing);
SpeedResult autocorrelation_speed(std::span< const double > x, double fs, double low, double high);
SpeedResult envelope_speed(std::span< const double > x, double fs, double carrier, double low, double high, double bandwidth);
struct CVSResult {
    core::Array                                          signal;
    std::vector< std::pair< std::size_t, std::size_t > > intervals;
    int                                                  cycles              = 0;
    double                                               coverage            = 0;
    std::size_t                                          completed_intervals = 0;
};
// 已验证相位单调、恒定相对转速、空间窗口无重叠；仅进行数值重组。
CVSResult cvs(std::span< const double > x, std::span< const double > carrier, std::span< const double > planet,
              double azimuth, double sensor, double half_width, int samples_per_revolution);
}    // namespace cnn_compute::rotation
