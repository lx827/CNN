#pragma once
#include <core/array.hpp>
#include <cstdint>
#include <memory>
#include <span>
#include <vector>

namespace cnn_compute::ica {
struct Options {int components=0,max_iterations=200;double tolerance=1e-6;std::uint64_t seed=0;};
struct Matrix {std::size_t rows=0,columns=0;std::vector<double> values;};
enum class Status {converged,iteration_limit,rank_deficient,singular_update};
struct Result {
    Matrix components,mixing,unmixing;
    core::Array mean;
    int numerical_rank=0,iterations=0;
    Status status=Status::iteration_limit;
};
// samples×channels行优先连续输入，只读借用至同步返回。中心化和白化副本属于
// 独占工作区；无全局RNG，seed只承诺本实现可重复，不锁定NumPy随机序列。
class Workspace {
public:
    struct Impl;std::unique_ptr<Impl> impl;
    Workspace();~Workspace();Workspace(Workspace&&) noexcept;
    Workspace& operator=(Workspace&&) noexcept;
    void prepare(std::size_t samples,std::size_t channels,std::size_t components);
};
// logcosh symmetric FastICA；SVD秩阈值eps*max(shape)*sigma_max，真实秩亏
// 保留状态，不以正则项制造观测维度。所有结果独立拥有，mixing恢复观测单位。
Result fast_ica(std::span<const double> observations,std::size_t samples,
                std::size_t channels,const Options& options = {});
namespace execution {
// 输入/形状/参数已验证；工作区独占。输出在入口构造最终拥有型矩阵，不返回
// 工作区view；SVD内部可以分配，z和逐轮投影/更新复用已准备容量。
Result fast_ica(std::span<const double> observations,std::size_t samples,
                std::size_t channels,const Options& options,Workspace& workspace);
}
}
