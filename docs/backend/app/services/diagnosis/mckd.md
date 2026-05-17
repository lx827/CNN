# `mckd.py` — MCKD 解卷积


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/mckd.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `mckd_deconvolution` | `mckd_deconvolution(signal, filter_len=30, T=1, M=1, max_iter=30) -> np.ndarray` | MCKD 最大相关峭度解卷积（引入故障周期约束） |
| `mckd_envelope_analysis` | `mckd_envelope_analysis(signal, fs, bearing_params, rot_freq, ...) -> dict` | MCKD + 包络分析 |
