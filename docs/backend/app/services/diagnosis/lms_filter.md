# `lms_filter.py` — LMS 自适应滤波


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/lms_filter.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `lms_filter` | `lms_filter(signal, reference, filter_order=32, mu=0.01) -> Tuple[np.ndarray, Dict]` | LMS 自适应滤波 |
| `nlms_filter` | `nlms_filter(signal, reference, filter_order=32, mu=0.01) -> np.ndarray` | 归一化 LMS |
| `vsslms_filter` | `vsslms_filter(signal, reference, filter_order=32, ...) -> np.ndarray` | 变步长 LMS |
