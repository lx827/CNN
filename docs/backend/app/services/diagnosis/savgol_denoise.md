# `savgol_denoise.py` — S-G 平滑


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/savgol_denoise.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `sg_denoise` | `sg_denoise(signal, window_length=51, polyorder=3) -> Tuple[np.ndarray, Dict]` | S-G 多项式平滑降噪 |
| `sg_trend_residual` | `sg_trend_residual(signal, window_length=501) -> Tuple[np.ndarray, np.ndarray]` | 趋势提取+残余分离 |
