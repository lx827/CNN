# `__init__.py` — 齿轮诊断公共接口


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/gear/__init__.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `compute_fm0` | `compute_fm0(tsa_signal, mesh_freq, sample_rate, n_harmonics=5) -> float` | FM0 粗故障检测 |
| `compute_er` | `compute_er(differential_signal, freq, amp, mesh_freq, rot_freq) -> float` | 能量比（多齿磨损） |
| `compute_ser` | `compute_ser(freq, amp, mesh_freq, rot_freq, n_sidebands=6) -> float` | 边频带能量比 |
| `analyze_sidebands` | `analyze_sidebands(freq, amp, mesh_freq, rot_freq, n_sidebands=6) -> dict` | 边频带分析 |
| `_evaluate_gear_faults` | `_evaluate_gear_faults(gear_result) -> Dict` | 齿轮故障评估 |

## `_evaluate_gear_faults` 指标阈值

**行星齿轮箱 FM4 阈值**（2025-05 调整）：
- `warning`: `fm4 > 3.2`（原 4.0）
- `critical`: `fm4 > 5.0`（原 7.0）
- 调整原因：WTgearbox 磨损样本 fm4 多分布在 3.2~4.5，原阈值漏检严重

**行星齿轮箱全频带包络峭度**（2025-05 新增）：
- `planetary_fullband_env_kurt` 指标基于 `planetary_fullband_demod.envelope_kurtosis`
- `warning`: `< 5.0`
- `critical`: `< 3.0`
- 用于 crack 检测（健康样本通常 > 6，crack 样本通常 < 4）
