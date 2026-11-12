#pragma once

#include <envelope/api.hpp>
#include <array>
#include <optional>
#include <span>
#include <vector>

namespace cnn_compute::emd {
using core::Array;

enum class StopMethod { sd, rilling, energy, fixed };
enum class Status { success, insufficient_extrema, iteration_limit, numerical_failure };
struct IMFOptions {
    double env_step_size = 1.0;
    int max_iters = 1000;
    double energy_thresh = 50.0;
    StopMethod stop_method = StopMethod::sd;
    double sd_thresh = 0.1;
    std::array<double, 3> rilling_thresh{0.05, 0.5, 0.05};
};
struct Options {
    IMFOptions imf;
    envelope::Options envelope;
    // 0 表示不限制 IMF 数量；能量/幅度阈值为 nullopt 表示不检查。
    int max_imfs = 0;
    std::optional<double> sift_thresh = 1e-8;
    std::optional<double> energy_thresh = 50.0;
    std::optional<std::array<double, 3>> rilling_thresh;
};
struct NextInfo {
    bool continue_flag = true;
    int iterations = 0;
    Status status = Status::success;
};
struct NextResult { Array imf; NextInfo info; };
struct Result {
    // 与 emd.sift.sift 一致，非零最终残差也是末列；每列独立拥有存储。
    std::vector<Array> components;
    std::vector<int> iterations;
    Status status = Status::success;
};

// 公开边界检查有限一维输入和参数；结果独立于输入与临时工作区。
NextResult get_next_imf(std::span<const double> signal, const IMFOptions& options = {},
                        const envelope::Options& envelope_options = {});
Result sift(std::span<const double> signal, const Options& options = {});
void validate(const IMFOptions& options, const envelope::Options& envelope_options);
void validate(const Options& options);

} // namespace cnn_compute::emd
