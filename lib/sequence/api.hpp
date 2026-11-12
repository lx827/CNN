#pragma once
#include <core/array.hpp>
#include <span>
#include <utility>

namespace cnn_compute::sequence {
// 所有输入为有限的一维序列，同步只读借用。结果独立拥有存储。
// execute 接口输入/输出不得重叠；输出容量由调用者准备，无全局状态或线程。
struct HoltResult { core::Array level, trend, season, fitted, forecast; };
struct KalmanResult { core::Array score, rate; double variance; };
struct CusumResult { double positive, negative, final_positive, final_negative, ewma; };
namespace execution {
void holt(std::span<const double> values, std::span<double> level,
          std::span<double> trend, std::span<double> season, std::span<double> fitted,
          std::span<double> forecast, double alpha, double beta, double gamma,
          int period, double initial_trend);
void kalman(std::span<const double> values, std::span<double> score,
            std::span<double> rate, double process_noise, double measurement_noise,
            double& final_variance);
}
HoltResult holt(std::span<const double> values, int steps, double alpha, double beta,
                double gamma, int period, double initial_trend);
KalmanResult kalman(std::span<const double> values, double process_noise, double measurement_noise);
CusumResult cusum(std::span<const double> values, double allowance = .5, double alpha = .2);
core::Array mann_whitney_z(std::span<const double> values, std::span<const double> reference, int window);
std::pair<double,double> regression(std::span<const double> x, std::span<const double> y);
// degree 中心矩，返回 {moment, variance}；scale=true 时先除最大绝对中心值。
std::pair<double,double> central_moment(std::span<const double> values, int degree, bool scale=false);
// 独立输出窗口RMS与Pearson峰度；尾部不足整窗不输出。
std::pair<core::Array,core::Array> window_moments(std::span<const double> values, int window);
}
