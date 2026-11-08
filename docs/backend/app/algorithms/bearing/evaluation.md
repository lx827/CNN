# `bearing/evaluation.py` — 包络指标评估

**对应源码**：`cloud/app/algorithms/bearing/evaluation.py`

## `evaluate_envelope`

```python
evaluate_envelope(analysis: EnvelopeAnalysis) -> EnvelopeEvaluation
```

只消费完整频谱对应的已有指标，不重新滤波或执行 FFT。

- 缺转频或全部目标不可分辨：`status="indeterminate"`，不表示健康。
- 单个理论频率超出分析带宽、共享 bin 或不可分辨：该项 `status="not_evaluable"`、`evaluable=False`、`significant=None`、`snr=None`，并给出 `reason`；不以 SNR=0 冒充未检出。没有局部峰但可分辨且无归属冲突时为 `evaluated=True、significant=False` 的有效阴性。
- 可评估物理峰的 `snr` 是局部峰/背景中位数的线性比，`snr_kind="linear_peak_to_background_not_db"`。
- `carrier_significant`、`sideband_significant` 和最终 `significant` 分开；主导过滤只作用于载波，BPFI 边带补救结果不会被覆盖。
- 统计显著性保留原始阈值结果，不因物理峰不显著而清零。
- 非 SNR 指标使用 `score`，不再把比例×10、峭度或峰值因子命名为 SNR。
- `rotation_harmonic_dominant` 仅由转频整数倍窄带能量比决定，与普通低频能量占比分开。有几何参数时统计键带 `_stat` 后缀（如 `low_freq_ratio_stat`），健康评分与 ensemble 均按该键读取；无参数时使用未后缀键。

## `evaluate_sideband_evidence`

```python
evaluate_sideband_evidence(evidence) -> dict
```

应用边带显著性规则，密度分母只包含可观测目标。无可观测目标时密度为 `None`；任一侧缺失时不对称度和 `high_asymmetry` 为 `None`。`snr_threshold=3`、`high_density` 和 `high_asymmetry` 判定仅属于本模块。
