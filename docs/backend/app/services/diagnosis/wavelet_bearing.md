# `wavelet_bearing.py` — 小波轴承分析


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/wavelet_bearing.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `wavelet_packet_bearing_analysis` | `wavelet_packet_bearing_analysis(signal, fs, bearing_params, ...) -> dict` | 小波包敏感节点包络分析 |
| `dwt_bearing_analysis` | `dwt_bearing_analysis(signal, fs, bearing_params, ...) -> dict` | DWT 敏感层包络分析 |
