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
