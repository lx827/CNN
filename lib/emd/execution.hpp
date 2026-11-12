#pragma once

#include <emd/api.hpp>
#include <envelope/execution.hpp>

namespace cnn_compute::emd {

struct Workspace {
    Array current, updated, upper, lower, average, residual;
    envelope::Workspace envelope;
    void prepare(std::size_t samples, int pad_width = 2);
};
namespace execution {
// 输入有限、参数已验证；output 长度等于输入且不与工作区重叠。
// input 在执行期间保持可读，不得借自会被更新的 current/updated/average 等缓冲。
// 工作区独占，不保存输入借用。失败后仍可 prepare 后再次使用。
NextInfo get_next_imf(std::span<const double> signal, std::span<double> output,
                      const IMFOptions& options, const envelope::Options& envelope_options,
                      Workspace& workspace);
// 返回独立拥有的列；workspace 可被后续调用覆盖。
Result sift(std::span<const double> signal, const Options& options, Workspace& workspace);
// 初次检查 initial=true 跳过能量和幅度终止测试，与上游一致。
bool check_continue(std::span<const double> original, std::span<const double> residual,
                    int layer, const Options& options, Workspace& workspace,
                    bool initial = false);
double standard_deviation(std::span<const double> signal);
double energy_difference(std::span<const double> signal, std::span<const double> residual);
double sum(std::span<const double> signal);
}
} // namespace cnn_compute::emd
