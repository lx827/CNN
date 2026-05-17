# `modality_bearing.py` — 模态分解轴承分析


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/modality_bearing.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `emd_bearing_analysis` | `emd_bearing_analysis(signal, fs, bearing_params, ...) -> dict` | EMD 敏感 IMF 包络分析 |
| `ceemdan_bearing_analysis` | `ceemdan_bearing_analysis(signal, fs, bearing_params, ...) -> dict` | CEEMDAN 敏感 IMF 包络分析 |
| `vmd_bearing_analysis` | `vmd_bearing_analysis(signal, fs, bearing_params, ...) -> dict` | VMD 敏感模态包络分析 |


## 内部辅助函数

### `_compute_envelope_spectrum`

```python
def _compute_envelope_spectrum(
    signal: np.ndarray,
    fs: float,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
) -> Dict
```

- **参数**:
  - `signal` (`np.ndarray`): 输入信号
  - `fs` (`float`): 采样率 (Hz)
  - `f_low_pass` (`float`): 包络低通截止频率 (Hz)
  - `max_freq` (`float`): 包络谱最大保留频率 (Hz)
- **返回值**：`{"envelope_freq": List[float], "envelope_amp": List[float]}`
- **说明**：Hilbert 变换求解析信号包络 → 去均值 → 可选低通滤波 → FFT 得到包络谱，返回频率和幅值列表

### `_reconstruct_selected_components`

```python
def _reconstruct_selected_components(
    components: List[np.ndarray],
    indices: List[int],
    target_length: int,
) -> np.ndarray
```

- **参数**:
  - `components` (`List[np.ndarray]`): 分量列表（IMF 或 VMD 模态）
  - `indices` (`List[int]`): 选中分量的索引
  - `target_length` (`int`): 重构信号目标长度
- **返回值**：`np.ndarray` — 重构的窄带信号
- **说明**：将选中的敏感分量叠加求和。若结果长度不足 target_length，则前端补零；若超过则截断
