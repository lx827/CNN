#pragma once
#include <core/array.hpp>
#include <memory>
#include <span>
#include <vector>

namespace cnn_compute::deconvolution {
struct Options {
    int filter_length = 64, max_iterations = 30;
    double tolerance = 1e-6, ridge = 1e-8;
};
struct Info { int iterations = 0; bool converged = false; };
struct Result {
    core::Array signal, filter;
    std::vector<double> objective_history;
    Info info;
};
// 每个活跃任务独占工作区；prepare 借用输入到返回，并保存必要的去均值副本、
// N×L 卷积矩阵及一次 QR/小R的SVD。相同输入的迭代复用分解，不物化薄U。
// prepare 可能分配；失败后可再次 prepare。输出不借用工作区。
class Workspace {
public:
    struct Impl;
    std::unique_ptr<Impl> impl;
    Workspace(); ~Workspace();
    Workspace(Workspace&&) noexcept;
    Workspace& operator=(Workspace&&) noexcept;
    void prepare(std::span<const double> signal, const Options& options);
};
// MED 为全局归一化峭度；MCKD 为显式周期留一乘积相关峭度，二者不混用目标。
// 输入一维有限、N>=64、2<=L<N/2。零能量抛 domain_error，数值求解失败抛 runtime_error。
Result med(std::span<const double> signal, const Options& options = {});
Result mckd(std::span<const double> signal, int period, int shift_order,
            const Options& options = {});
double normalized_kurtosis(std::span<const double> values);
double correlated_kurtosis(std::span<const double> values, int period, int shift_order = 1);
// 独立更新原语：X为rows×columns行优先，系数长columns；准备一次SVD后复用
// 与完整MCKD相同的留一乘积/求解实现，结果独立拥有。
core::Array mckd_update(std::span<const double> matrix,std::size_t rows,std::size_t columns,
                        std::span<const double> filter,int period,int shift_order,double ridge);
namespace execution {
// 先 prepare；output 长N、filter长L、history容量>=max_iterations；三者与工作区
// 互不重叠，计算直接写最终存储。history前info.iterations项有效，无分配迭代。
Info med(const Options& options, std::span<double> output, std::span<double> filter,
         std::span<double> history, Workspace& workspace);
Info mckd(int period, int shift_order, const Options& options,
          std::span<double> output, std::span<double> filter,
          std::span<double> history, Workspace& workspace);
}
}
