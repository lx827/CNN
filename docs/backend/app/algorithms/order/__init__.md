# `algorithms/order/` — 转速、相位与阶次算法

**对应源码**：`cloud/app/algorithms/order/`

独立纯计算包，不依赖 FastAPI、ORM、数据库、设备配置或故障增强算法。数组在算法层保持 NumPy 引用，只有业务/HTTP 适配层转换为列表或旧 tuple。

## 模块

- `types.py`：标量转频、局部转频序列、连续转速/相位、角域采样和 FFT 阶次谱的 dataclass 契约。
- `estimation.py`：频谱/包络/Welch/自相关标量候选仲裁，以及 STFT 连续转速脊线。
- `resampling.py`：恒速等角采样、连续转速梯形积分、等相位重采样、单边幅值阶次谱。
- `pipeline.py`：恒速、缓变、快速变速与自动判别 Pipeline。

## 不可混用的表示

1. `ScalarSpeed`：一个区间内的标量转频；未知时为 `status="indeterminate"` 且频率为 `None`。
2. `LocalSpeedEstimates`：逐帧局部转频和可靠/保留掩码；只用于缓变分帧谱平均，不含连续相位。
3. `SpeedTrajectory` + `PhaseTrajectory`：连续时间转速及累计转数，用于快速变速等相位重采样。
4. `AngleDomainSignal.angle_revolutions`：等角采样点位置，间隔 `1/samples_per_revolution`。
5. `OrderSpectrum.order_bins`：角域 FFT bin 阶次，间隔 `samples_per_revolution/N`。它与上一轴不是同一对象。

`OrderAnalysis` 将上述实际表示与有效性一起传给下游。`multi_frame` 的 `phase/angle_domain` 必为 `None`，防止把逐帧谱平均误认为连续相位补偿。`TachometerPulses` 只为未来独立 tach 输入保留类型，当前 Pipeline 未实现也不接受 tach。

## 工况边界

- 已知准确转频：`ConstantSpeedOrderPipeline`，无需 tach。
- 未知或缓变：`SlowVaryingSpeedOrderPipeline`，分帧估计、MAD 异常帧处理、逐帧阶次谱平均。
- 快速变速：`FastVaryingSpeedOrderPipeline`，STFT 脊线→连续转速→积分相位→等相位重采样。
- 自动模式只有在至少两个有效局部估计且 CV 不超阈值时才接受缓变；单帧、slow 失败或快速变速都会尝试 fast，脊线不可靠则返回 `indeterminate`，不得退回多帧正常谱。

当前只有 `/order` 接入完整快速变速结果。齿轮 TSA、行星解调等仍要求标量恒速/缓变输入，Engine 会明确拒绝快速变速，不能声称这些下游已经支持连续相位。
