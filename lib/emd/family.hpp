#pragma once

#include <emd/sifting.hpp>
#include <cstdint>

namespace cnn_compute::emd::family {

// 业务 Huang/Wu/Torres 族；与 emd::Options 的 emd.sift 0.8.1 公式独立。
enum class Method { emd,
                    eemd,
                    ceemdan };
enum class Reason { none,
                    zero_variance,
                    insufficient_extrema,
                    no_valid_ensemble_member,
                    maximum_sifts_reached };
struct Options {
    SiftParameters sift{ 100, 3, 0.2 };
    int            max_imfs      = 8;
    int            ensemble_size = 50;
    double         noise_scale   = 0.2;
};

// 每个 IMF 和 residual 独立拥有 N 个 double，与输入及工作区无别名。
// 空 imfs 表示不可判定；未收敛仍返回近似模态及逐模态迭代/质量状态。
// 非有限的中间计算抛异常，不伪装为成功结果。
struct Result {
    std::vector< Array > imfs;
    Array                residual;
    std::vector< int >   iterations;
    std::vector< bool >  converged;
    Reason               reason = Reason::none;
};

struct DecompositionWorkspace {
    SiftWorkspace sift;
    Array         residual, mode;
};

// 每个活跃调用独占，允许顺序跨规模复用；异常后也可重新执行。
// 输入只读借用到同步调用返回；内部不创建线程、全局 RNG 或全局工作区。
// EEMD 只保留逐模态累加；CEEMDAN 缓存 M 条白噪声和至多 M*(K-1)
// 条标准化噪声 IMF。缓存随本次执行结束释放，不跨任务累计。
struct Workspace {
    DecompositionWorkspace decomposition;
    Array                  normalized, residual, trial;
    std::vector< int >     members;
};

// 公开入口扫描一次有限输入(N>=8)，检查算法参数，再调用 execution。
// seed 是任意长度非负整数的小端 uint32 limbs，由 seed_seq 初始化
// mt19937_64；正态采样使用当前 C++ 标准库，保证同构建同种子可复现，
// 不承诺与 NumPy 或不同标准库的随机序列相同。空 seed 表示整数 0。
Result decompose(std::span< const double > signal, Method method, const Options &options = {},
                 std::span< const std::uint32_t > seed = {});

namespace execution {
    // 调用方已建立公开前提；result 与输入/workspace 不重叠。
    // 直接写入 result 的最终 owner，复用工作区；结果不借用工作区。
    // 首次/规模变化准备 O(N) 缓冲；动态模态结果在首次产生该阶时分配。
    void decompose(std::span< const double > signal, Method method, const Options &options,
                   std::span< const std::uint32_t > seed, Result &result, Workspace &workspace);
}    // namespace execution

}    // namespace cnn_compute::emd::family
