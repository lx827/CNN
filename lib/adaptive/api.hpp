#pragma once
#include <core/array.hpp>
#include <span>

namespace cnn_compute::adaptive {
enum class Method { lms, nlms, variable_step };
struct Options {
    Method method=Method::lms;
    int filter_length=32, delay=1;
    // 0为全段；非零为最多更新次数，之后继续用最终权重滤波。
    std::size_t max_updates=0;
    double step_size=0.01, alpha=0.97, gamma=5e-5, minimum_step=1e-6, maximum_step=0.05;
};
struct Workspace {
    core::Array reference, weights;
    // 分配N和L；独占、无输入借用留存，调用结束后可再次prepare。
    void prepare(std::size_t samples,int filter_length);
};
// 输入有限、N>L+delay，输出独立拥有。零延迟允许；不自动创建线程。
core::Array filter(std::span<const double> input,const Options& options = {});
namespace execution {
// output长N，与输入/工作区不重叠；参数已经验证，工作区已prepare。
// 无循环分配；最终去均值，前L点沿用输入后参与去均值。
void filter(std::span<const double> input,std::span<double> output,const Options& options,Workspace& workspace);
}
}
