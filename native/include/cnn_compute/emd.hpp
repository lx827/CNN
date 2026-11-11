#pragma once

#include <Eigen/Core>
#include <optional>
#include <span>

namespace cnn_compute::emd {

using Array = Eigen::ArrayXd;
struct SiftParameters {
    int max_sifts;
    int mirror_extrema;
    double sd_threshold;
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
std::optional<Envelopes> envelopes(std::span<const double> signal, int mirror_extrema);
// 调用者保证节点严格递增；查询顺序任意，首尾段多项式承担外推。
Array pchip(std::span<const double> x, std::span<const double> y, std::span<const double> query);

} // namespace cnn_compute::emd
