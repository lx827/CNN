# 原生旋转机械与序列计算验收（2026-11-13）

本页记录 #126 原生转速/阶次、齿轮表示、AM/FM/CVS 和趋势序列计算的 Windows 验收。数学前提与状态仍以[阶次契约](INDEX.md)、[齿轮契约](../gear/INDEX.md)及[复合研究契约](../composite/INDEX.md)为准。

## 数值与接口

通过既有公开 cloud 调用执行原生 4 项独立向量、阶次 17 项、定轴齿轮 13 项、行星 19 项及 AM/FM/CVS 7 项，共 60 项。定轴“已有分析重评不重做 FFT”的测试原先拦截已移除的 SciPy 导入名，现拦截真实原生幅值入口；修正后单独复查通过，未放宽原有数值预算。

另通过 7 个公开数值边界操作及现有趋势 6 个向量，覆盖 NaN 不得变成零 CUSUM/空谱峰、退化/稳定预测、单点/空序列和 Kalman 平滑。测试入口为 `cloud/tests/diagnosis/algorithms/test_native_rotation.py`、`test_order_pipeline.py`、`test_fixed_axis_gear.py`、`cloud/tests/diagnosis/planetary/test_planetary_pipeline.py`、`cloud/tests/diagnosis/algorithms/test_composite_pipelines.py` 的 AMFM/CVS 类及 `foundation/layer1/test_trend_prediction_correctness.py`。

绑定仅检查维度、布局和最小长度，数值前提由公开 C++ 入口统一建立。候选组合复用已验证且中心化的输入，窗口矩组合不重复执行全数组检查；滤波/Hilbert 组合调用内部执行接口。输入同步只读借用，独立输出 capsule 在最后一个 NumPy 数组或 view 释放时销毁；没有全局可写工作区或新增线程。

## 公开调用耗时

环境为 Windows x64、MSVC 19.50.35730、baseline、`/O2 /fp:strict`，Python 3.13.15、NumPy 2.5.4、SciPy 1.18.1。baseline 构建报告 SSE2；本次没有逐内核 SIMD 证据，不据此宣称所有路径均已向量化。

Python 对照直接读取提交 `a3cef06` 的原公开实现。两侧各预热一次，随后三个交错计时块各调用一次，表中为中位数；计时包含真实公开入口的布局适配、参数处理和结果对象构造，输入为相同连续 float64 数组。TSA 对照同时使用该提交的原阶次谱实现，避免对照过程混用新后端。

| 公开能力与输入 | Python 对照 | 原生 | 倍数 |
|---|---:|---:|---:|
| 标量转速仲裁，8192 点、2048 Hz | 5.609 ms | 2.506 ms | 2.24× |
| CZT，8192 点、1024 个输出点、460–500 Hz | 1.442 ms | 0.943 ms | 1.53× |
| TSA 表示，1024 点/转、32 转、啮合 20 阶与三次谐波 | 1.264 ms | 0.588 ms | 2.15× |
| Kalman 健康序列，1000 点 | 19.710 ms | 0.497 ms | 39.63× |

相同输入的转速两侧均为 24 Hz；CZT 幅值最大绝对差 `7.56e-11`，TSA 幅值谱最大绝对差 `4.82e-17`，Kalman 既有舍入响应逐项一致。TSA 还验证单圈 DFT 推导的长记录周期 Hann 谱、mesh/regular/residual/differential 恒等式及输出生命周期。CZT 的非 FFT 网格另与直接 DFT 比较。

### CZT 端点刻度数学修正

官方 [SciPy 1.18.1 `ZoomFFT` 源码](https://github.com/scipy/scipy/blob/v1.18.1/scipy/signal/_czt.py)规定 `endpoint=False` 不包含频带上限，实际点为 `low+k*(high-low)/m`、`0<=k<m`。本库限制 `high<=fs/2`，因此输出没有 Nyquist 点；只有真正 `low==0` 的 DC 点取消单边翻倍。

旧 Python 及最初原生移植使用 `isclose` 将非常接近 Nyquist 的普通正频点误当端点，或将接近零的正频点当 DC。这次明确修正该数学缺陷，不把它当作兼容义务。新增独立端点向量采用 `fs=2048 Hz`、`N=262144`、16 点网格，上限为 `1024 Hz`，末点为 `1023.9921875 Hz`：该处单位正弦的峰值幅值应为 **1**，不能折半；真正 DC 的单位常数幅值仍为 **1**。该补充向量不计入前述 60 项统计，不改变前表普通频带的性能测量。

## 内存与限制

TSA 在两个独立进程内使用相同导入、输入准备、一次预热和一次结果存活的公开调用，Windows OS `PeakWorkingSetSize` 分别为 Python 对照 **107.44 MiB**、原生 **106.10 MiB**。此数字含解释器与数值库导入，不将全部差额归因于算法缓冲。

上述 TSA 输入为 256 KiB，四个完整信号输出共 1 MiB。阶次幅值使用独立完整半谱的前缀 view，保留底层半谱 owner；不能仅以截断 view 的 `nbytes` 当作实际拥有的分配量。STFT 复用单帧临时数组，仅存可靠脊线和最终轨迹，不持有完整时频矩阵。公开结果、工作区与输入存储分开，TSA 输出没有借用下一次调用会覆盖的工作区。

原始计时与测量脚本保留在本机忽略目录 `build/rotation-validation/`，不提交自动报告。这些结果限定于所列输入和 Windows 构建；不是分类准确率、Linux/ARM 验证或 ECS/树莓派整机资源验收。
