# `bearing_cyclostationary.py` — 轴承循环平稳分析


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/bearing_cyclostationary.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `bearing_sc_scoh_analysis` | `bearing_sc_scoh_analysis(signal, fs, bearing_params, rot_freq) -> dict` | 谱相关/谱相干循环平稳分析 |


## 内部辅助函数

### `_compute_sc_scoh_bearing`

```python
def _compute_sc_scoh_bearing(
    signal: np.ndarray,
    fs: float,
    seg_len: int = 2048,
    overlap_ratio: float = 0.75,
    alpha_max: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]
```

- **参数**:
  - `signal` (`np.ndarray`): 输入信号
  - `fs` (`float`): 采样率 (Hz)
  - `seg_len` (`int`): 分段 FFT 长度
  - `overlap_ratio` (`float`): 分段重叠比例
  - `alpha_max` (`Optional[float]`): 最大循环频率，None 则取 fs/4
- **返回值**：`(f_axis, alpha_axis, scoh_matrix)`
  - `f_axis` (`np.ndarray`): 载波频率轴
  - `alpha_axis` (`np.ndarray`): 循环频率轴
  - `scoh_matrix` (`np.ndarray`): 谱相干矩阵，形状 `(n_alpha, n_freq)`，值域 [0, 1]
- **说明**：分段 FFT 估计法计算谱相关密度和谱相干。对每段加 Hanning 窗做 FFT，累加复数交叉谱 `X(f-α/2)·conj(X(f+α/2))`，最终谱相干为 `|SC|² / (PSD_lo · PSD_hi)`。非循环频率处相位随机平均后趋零，真实循环频率处相位对齐出现显著峰值
