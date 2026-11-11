#pragma once

#include <Eigen/Core>
#include <optional>
#include <span>
#include <array>

namespace cnn_compute::emd {

using Array = Eigen::ArrayXd;
enum class Interpolation { pchip, cubic };
enum class StoppingRule { sd, rilling };
struct SiftParameters {
    int max_sifts;
    int mirror_extrema;
    double sd_threshold;
    Interpolation interpolation = Interpolation::pchip;
    StoppingRule stopping_rule = StoppingRule::sd;
    std::array<double, 3> rilling_thresholds{0.05, 0.5, 0.05};
};
struct SiftResult {
    Array imf;
    int iterations;
    bool converged;
};
struct Envelopes {
    Array upper;
    Array lower;
};

// 输入契约由 Python 边界保证：一维有限 double、有效参数，内部不重复校验。
std::optional<SiftResult> sift(std::span<const double> signal, const SiftParameters& parameters);
std::optional<Envelopes> envelopes(std::span<const double> signal, int mirror_extrema,
                                 Interpolation interpolation = Interpolation::pchip);
// 调用者保证节点严格递增；查询顺序任意，首尾段多项式承担外推。
Array pchip(std::span<const double> x, std::span<const double> y, std::span<const double> query);
Array cubic(std::span<const double> x, std::span<const double> y, std::span<const double> query);
bool rilling_stop(std::span<const double> upper, std::span<const double> lower,
                  const std::array<double, 3>& thresholds);

} // namespace cnn_compute::emd
