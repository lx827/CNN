# `bss.py` — 盲源分离

**对应源码**：`cloud/app/services/diagnosis/bss.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `fast_ica` | `fast_ica(X, n_components, max_iter=200, tol=1e-4) -> np.ndarray` | FastICA 算法 |
| `vmd_ica_separation` | `vmd_ica_separation(signal, fs, K=5, alpha=2000, ...) -> np.ndarray` | VMD+ICA 单通道扩展盲分离 |
