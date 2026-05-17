# `bearing_sideband.py` — 轴承边带


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/bearing_sideband.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `compute_sideband_density` | `compute_sideband_density(envelope_freq, envelope_amp, fault_freq, rot_freq) -> dict` | 边频密度 |
| `evaluate_bearing_sideband_features` | `evaluate_bearing_sideband_features(...) -> dict` | 边频特征评估 |
