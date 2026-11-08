# `order_tracking.py` — 旧阶次 tuple 兼容边界

**对应源码**：`cloud/app/services/diagnosis/order_tracking.py`

本文件不再包含转频估计、重采样或 FFT 数学实现；唯一实现位于 [`algorithms/order/`](../../algorithms/order/__init__.md)。保留它只为行星解调等尚未结构化的旧调用方转换返回值，新代码应直接使用 `OrderAnalysis`。

## 适配函数

- `_order_tracking(sig, fs, rot_freq, samples_per_rev=1024)`：委托恒速 Pipeline，返回 `(角域信号, 角域采样点轴)`。第二轴单位为 rev，间隔 `1/samples_per_rev`；旧版把它同时当 FFT 阶次轴的语义已删除。
- `_compute_order_spectrum(...)`：返回 `(FFT bin 阶次轴, 单边峰值幅值)`，默认保留到 `max_order=50`。
- `_compute_order_spectrum_multi_frame(...)`：返回 `(阶次轴, 幅值, 保留局部转频中位数, 标准差)`；内部仍是局部序列，不表示连续相位。
- `_compute_order_spectrum_varying_speed(...)`：返回 `(阶次轴, 幅值, 连续轨迹中位数, 标准差)`；中位数仅供旧摘要，不能反推相位。

所有适配在 `OrderAnalysis.status != "valid"` 时抛出 `ValueError`，不得把不可判定结果替换为默认转频或正常空谱。显式传入旧 `nperseg/noverlap` 时只转换为 STFT 参数；缺省使用按采样率自适应窗长。
