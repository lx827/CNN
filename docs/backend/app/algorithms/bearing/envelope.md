# `bearing/envelope.py` — 标准包络计算

**对应源码**：`cloud/app/algorithms/bearing/envelope.py`

## `EnvelopeParameters`

```python
EnvelopeParameters(
    band_center_hz: float | None = None,
    band_width_hz: float | None = None,
    envelope_low_pass_hz: float = 2000.0,
    filter_order: int = 4,
)
```

算法参数不包含展示上限。完整有效包络频带由包络低通截止频率和 Nyquist 决定，API 的 `max_freq` 只在业务层截断展示。

## `compute_envelope`

```python
compute_envelope(signal, sample_rate_hz, parameters=None) -> EnvelopeRepresentation
```

执行：去均值 → Butterworth SOS 带通 → Hilbert 包络 → 低通 → 去直流 → 周期 Hann → 单边幅值谱。

- 幅值使用 `2 / sum(window)` 相干增益补偿，DC/Nyquist 不翻倍，单位与输入信号一致，`scaling="single_sided_amplitude"`。
- 低采样率默认频带为 Nyquist 的 25%～75%；较高采样率优先 2000～4000 Hz，无法覆盖时退回采样率相对频带。
- 请求频带裁到可实现范围后，返回值中的 `band` 是实际滤波频带。
- 输入必须是一维、至少 64 点、全部为有限值，采样率为正。滤波器阶数为正整数，低通截止频率为有限正数。
- 非法输入抛出 `ValueError`，不跳过滤波或默认成健康。

`EnvelopeRepresentation` 包含完整有效 `spectrum`、实际 `band`、`envelope_low_pass_hz` 和 `sample_rate_hz`。
