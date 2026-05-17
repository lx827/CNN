# `bss.py` — 盲源分离


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/bss.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `fast_ica` | `fast_ica(X, n_components, max_iter=200, tol=1e-4) -> np.ndarray` | FastICA 算法 |
| `vmd_ica_separation` | `vmd_ica_separation(signal, fs, K=5, alpha=2000, ...) -> np.ndarray` | VMD+ICA 单通道扩展盲分离 |
