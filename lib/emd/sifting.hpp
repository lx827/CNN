#pragma once

#include <emd/emd.hpp>
#include <emd/extrema.hpp>

namespace cnn_compute::emd {

// 每个活跃调用独占；current/updated 为必要可写副本，包络和节点容量跨
// 筛分、模态、成员复用。失败或异常后可重新调用；不保存输入或输出 view。
struct SiftWorkspace {
    Array             current, updated;
    detail::Workspace envelope;
};

struct SiftInfo {
    int  iterations;
    bool converged;
};

namespace execution {
    // 已建立有限一维输入及有效参数；out 等长且与输入/工作区不重叠。
    // 输出直接写入调用者存储，初始极值不足时返回空且不写 out。
    // 首次/规模变化/节点容量增长可能分配，其余缓冲跨调用复用。
    std::optional< SiftInfo > sift(std::span< const double > signal, std::span< double > out,
                                   const SiftParameters &parameters, SiftWorkspace &workspace);
}    // namespace execution

}    // namespace cnn_compute::emd
