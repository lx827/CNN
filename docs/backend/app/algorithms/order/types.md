# `types.py` — 转速/相位数据契约

**对应源码**：`cloud/app/algorithms/order/types.py`

## 参数类型

- `SpeedSearchRange(low_hz=10, high_hz=100)`：转频搜索范围。
- `OrderParameters(samples_per_revolution=1024, max_order=50)`：角域采样率和谱展示上限；`max_order` 必须低于角域奈奎斯特阶次。
- `FrameParameters`：帧长、重叠率、MAD 阈值、相对/绝对 MAD 下限和快速变速 CV 阈值。
- `RidgeParameters`：目标频率分辨率、最长 STFT 窗时长、重叠率、脊线可靠性阈值、连续边界帧数与边界帧比例上限。默认目标 0.5 Hz、最长 0.5 秒；实际物理分辨率为 `fs/nperseg`，零填充或抛物线插值不改变它。

## 结果类型

| 类型 | 关键字段 | 语义 |
|------|----------|------|
| `ScalarSpeed` | `frequency_hz/source/status/reason` | 标量转频或明确不可判定 |
| `LocalSpeedEstimates` | 帧时间、频率、可靠/保留掩码 | 多帧局部估计，可计算保留帧中位数和标准差 |
| `SpeedTrajectory` | `time_s/frequency_hz`、STFT 实际参数 | 连续时间转速轨迹 |
| `PhaseTrajectory` | `time_s/revolutions` | 从零开始严格递增的累计转数；`phase_rad` 按需计算 |
| `AngleDomainSignal` | `angle_revolutions/samples` | 等角采样信号及采样位置轴 |
| `OrderSpectrum` | `order_bins/amplitude/order_resolution` | FFT 阶次轴和输入单位下的单边峰值幅值 |
| `OrderAnalysis` | `status/tracking_method/speed/spectrum/phase/angle_domain` | 完整结果及下游可用性 |

不可靠局部帧以 NaN 占位并由掩码排除，不能参与中位数或标准差。所有 dataclass 在构造时检查维度、长度、单位相关约束和有限值；构造本身不复制数组。
