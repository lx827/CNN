# `bearing/analysis.py` — 包络原始指标分析

**对应源码**：`cloud/app/algorithms/bearing/analysis.py`

## `analyze_envelope_spectrum`

```python
analyze_envelope_spectrum(
    spectrum: Spectrum,
    geometry: BearingGeometry | None = None,
    rot_frequency_hz: float | None = None,
    rot_frequency_std_hz: float = 0.0,
) -> EnvelopeAnalysis
```

从完整有效包络频带提取原始指标，不执行 FFT，也不受 API 展示截断影响。

- 先在容差内收集局部峰，再按幅值、归一化距离做全局唯一分配；偏移真峰不会因最近 bin 不是局部峰而漏检。
- 共享 bin 且未获得唯一归属的目标记录 `peak_issues`；无局部峰但可分辨的目标是有效阴性，不是不可评估。
- `SidebandEvidence` 分离 `observable_targets` 与实际局部峰 `observations`；所有在频带内、可分辨且唯一归属的理论目标都进入密度分母，包括无局部峰/不显著目标。
- 搜索容差只覆盖最近 bin、3% 工程容差和转频不确定性，不使用 `2df` 宽窗。
- `spectral_power_proxy` 是幅值平方和，`spectral_power_unit` 为输入幅值单位平方；不声称是时域物理能量。
- `low_frequency_ratio` 与 `rotation_harmonic_energy_ratio` 分离，后者只累计转频整数倍附近的唯一 bin。

## `compute_sideband_metrics`

```python
compute_sideband_metrics(observations, observable_targets) -> SidebandEvidence
```

只根据可观测边带计算不对称度；任一侧缺失时 `asymmetry=None`。边带密度及显著性由 `evaluation.py` 计算。

## `EnvelopeFeatures.as_dict`

输出 `spectral_power_proxy`、`spectral_power_unit` 和故障频率/谐波能量比，不再输出 `total_env_energy`。
