# `pipeline.py` — 三种阶次分析 Pipeline

**对应源码**：`cloud/app/algorithms/order/pipeline.py`

## `ConstantSpeedOrderPipeline.run(signal, fs, speed)`

要求有效 `ScalarSpeed`。已知准确转频时直接等角采样并计算阶次谱；未知/非法转频不会默认 10 Hz。结果含标量速度、连续相位、角域信号和阶次谱。

## `SlowVaryingSpeedOrderPipeline.run(signal, fs, estimation_signal=None)`

逐帧估计局部标量转频。`select_retained_speed_frames` 使用 `max(mad_threshold*MAD, relative_mad_floor*median, absolute_mad_floor_hz)` 作为异常帧容差；即使 MAD=0，0.05 Hz 绝对下限与 1% 相对下限仍能排除真正离群帧，同时保留正常微小变化。各保留帧独立等角重采样、计算单边幅值谱，再插值到公共 FFT 阶次轴做幅值平均。

结果只含 `LocalSpeedEstimates` 和平均谱；`phase/angle_domain=None`，因为该流程不是连续相位跟踪。

## `FastVaryingSpeedOrderPipeline.run(signal, fs, estimation_signal=None)`

执行 STFT 脊线→连续转速→梯形积分相位→等相位重采样→阶次谱。任一步失败返回 `indeterminate`，不退回标量恒速。

## `AutomaticOrderPipeline`

先运行缓变 Pipeline。只有至少两个有效局部估计且 `std/median <= 0.10` 时才返回缓变结果。单帧 `std=0` 不能证明恒速，slow 估计失败、有效帧不足或 CV 超阈值都会继续尝试 fast；fast 也失败时返回带原因的不可判定结果，不能保留 slow 谱冒充成功。

`estimation_signal` 是未做故障增强的原始/去趋势信号；`signal` 可为调用方显式选择的去噪信号。二者必须等长。
