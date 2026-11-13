# 完整原生业务 EMD 族

## 数学目的与范围

云端默认 `NativeEMDImplementation` 经 `cnn_compute.emd_family` 一次调用完成 EMD、EEMD 或 Torres 2011 CEEMDAN。归一化、完整 IMF 筛分、多模态残差更新、随机噪声、逐模态集成及质量信息均在 C++；Python 负责配置、布局转换、Hz/有效区间和领域结果适配。后续敏感分量选择、阈值及诊断继续属于各自 Pipeline。

数学参照是仓库内 [Python 实现](../../../cloud/app/algorithms/decomposition/emd/python_adapter.py)，支持 PCHIP/cubic 与 SD/Rilling。该族不混用 [emd.sift 0.8.1 原生候选](native_emd.md) 的极值、延拓与局部均值公式。原参考可显式注入，默认执行不回退 Python。

## 适用场景与必要前提

用于非平稳信号探索、敏感 IMF 与去噪；模态混叠和端点效应仍存在，不以分解成功代替物理故障依据。输入有限、至少八点、采样率为正；算法参数前提由公开 C++ 入口建立，内部热路径沿用。参数及真实函数签名以 [包 docstring](../../../cnn_compute/emd_family.py) 和 [C++ 头](../../../lib/emd/family.hpp) 为准。

## 公式与随机性

- EMD 按输入最大幅值归一化；接受 SD/Rilling 所决定的本轮更新，逐阶减去 IMF，极值不足即停止。
- EEMD 对输入标准差归一化，添加相应比例的高斯噪声；每阶只对实际存在该阶 IMF 的成员平均。按模态逐成员累加，不保留完整成员结果池。
- CEEMDAN 第一阶添加原白噪声，之后添加对应白噪声 IMF 的标准化分量，幅值随当前残差标准差缩放。平均的是每次试验的第一 IMF，符合 Torres 2011，未换成 improved-CEEMDAN 的局部均值平均。
- 零噪声 EEMD/CEEMDAN 直接复用基础 EMD；无噪声缓存及随机生成开销。

随机数在 C++ 调用局部生成：任意长度非负 Python 整数转成小端 uint32 limbs，`seed_seq` 初始化 `mt19937_64`，使用标准库 `normal_distribution`。相同构建/输入/配置/种子可复现；NumPy 与 C++ 序列、不同 C++ 标准库之间的正态序列不承诺逐点相同。此变化不改变高斯噪声分布或集成公式，但同种子重新诊断的 IMF 可能与迁移前不同，旧缓存不会自动重算。取舍见 [ADR 0010](../../adr/0010-complete-business-emd-native.md)。

## 模块依赖与数据所有权

```text
cloud NativeEMDImplementation（Hz/结果适配）
  → cnn_compute.emd_family（配置/一次布局转换）
    → bind/emd_business.cpp（GIL/capsule）
      → emd::family::decompose（公开前提/拥有型结果）
        → family::execution::decompose（完整流程/逐成员聚合）
          → emd::execution::sift（当前/更新/包络工作区复用）
            → 极值插值包络 → interpolation::execution → solvers
```

合规连续 float64 输入只读借用到同步调用返回。非连续或其它 dtype 在 Python 边界集中转换一次。C++ 可写归一化、残差、试验、筛分数组是算法所需工作副本；工作区跨成员和模态复用。极值/节点容量增长和信号规模变化可重新分配，已准备的同规模筛分缓冲复用；不承诺动态节点全过程零分配。

最终 IMF 与残差独立拥有 Eigen 存储，经 capsule 移动交给 NumPy；不复制为二维矩阵、不暴露工作区指针。下次调用、工作区复用或销毁不会覆盖结果。每个活跃调用独占工作区，失败后可重新调用；不创建内部线程、全局 RNG 或全局可写工作区。

## 输出、单位与失败状态

IMF、残差保持原输入长度、采样率和物理幅值单位；有效区间为全长半开区间。返回实际筛分次数与逐模态收敛标志。常量返回 `zero_variance`，基础无模态返回 `insufficient_extrema`，随机集成无合法成员返回 `no_valid_ensemble_member`，均保留原残差并标为不可判定。

迭代耗尽保留近似 IMF 与 `maximum_sifts_reached`，既有 Pipeline 仍按选中模态收敛状态拒绝质量不足结果。插值或集成产生非有限值直接抛异常，不能吞掉为成功去噪。

## 复杂度与内存

记长度 N、最大 IMF 数 K、成员数 M。输入约 8N 字节，最终 IMF 与残差至多 `8N(K+1)`；基础归一化/残差/筛分和包络/节点/插值工作区为 O(N)，常数项由真实极值数量与插值决定。

EEMD 结果累加池为 O(NK)，不再保留 O(NKM) 的成员结果。CEEMDAN 为每成员缓存一条白噪声及最多 K−1 条必要噪声 IMF，噪声缓存上界为 `8NMK`，不把它误称为 O(N)。例如 N=128000、K=8、M=30，输入约 0.98 MiB、结果约 8.79 MiB、噪声缓存上界 234.38 MiB，另计所有工作区、Python 进程和同时活跃调用。基础与 EEMD 不分配这份 CEEMDAN 缓存。

遵守现有两线程池和逐批串行，不增加生产并发额度。上述存储算账不是目标 ECS 整机峰值验收，也不构成任意输入/参数的 2 GiB 保证。

## 验证向量与验证状态

- [原生差分](../../../cloud/tests/diagnosis/algorithms/test_native_emd.py)：确定性 EMD 四种筛分组合对显式 Python 参考，保留既定数组预算；随机集成检查四种配置复现、完整性和质量元数据。需要数据根的旧五向量仅作确定性/零噪声对照。
- [完整业务入口](../../../cloud/tests/diagnosis/algorithms/test_native_emd_family.py)：禁止调用 Python 数值实现/NumPy RNG、非连续输入保留、owner 生命周期、超长种子、零噪声、数值失败、尺度与未收敛状态。
- [纯 C++ 契约](../../../tests/native/emd_business_contract.cpp)：用相同原生白噪声和独立基础 EMD 调用组成 EEMD/Torres CEEMDAN 公式参照；检查公开/内部入口、跨规模工作区、失败后复用、并发隔离和重构。
- [测量脚本](../../../scripts/benchmark_emd_family.py)：每算法/后端独立进程，端到端计时计入参数/布局/所有权，OS 峰值包含导入、预热与真实输出生命周期。随机源不同，不将混合/原生的耗时差全部归因于接口开销。

2026-11-14 Windows MSVC 19.50 baseline SSE2 首轮测量，4096 点、最多四 IMF、八成员、50 次筛分上限，各后端预热后测三次：

| 算法 | 旧混合中位 ms | 完整原生中位 ms | 旧混合/原生 OS 峰值 MiB |
|---|---:|---:|---:|
| EMD | 0.27 | 0.16 | 78.00 / 78.10 |
| EEMD | 9.22 | 7.99 | 79.75 / 78.57 |
| CEEMDAN | 25.19 | 17.47 | 80.20 / 79.43 |

同一合成规格在 WSL Ubuntu 22.04、GCC 11.4 baseline SSE2 上，旧混合→完整原生中位耗时分别为 EMD 0.22→0.09 ms、EEMD 6.39→5.19 ms、CEEMDAN 18.97→14.29 ms；OS 峰值分别为 79.90/80.18、81.96/81.02、81.92/81.73 MiB。Windows 的 `family.cpp` 目标文件反汇编观察到 `mulpd/divpd/addpd/subpd` 批量数值指令，不据此声称随机生成、索引压缩或全部算法路径均已向量化。

Windows MSVC 与 Linux GCC 的完整 Python 扩展构建、纯 C++ 公式/生命周期契约和上述云端定向检查通过；Windows 三项 P0 通过。两项依赖数据根的固定真实向量检查未运行。该少量测量不代表生产 SLO、真实数据诊断效果、ECS 资源验收或 ARM64 支持。实际构建与验收记录随 PR 保存。
