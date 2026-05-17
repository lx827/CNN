# `msb.py` — 双谱分析


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/gear/msb.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `msb_residual_sideband_analysis` | `msb_residual_sideband_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | MSB-SE 残余边频带分析 |

| `_compute_slice_snr` | `_compute_slice_snr(msb_se_slice: np.ndarray, fc_axis: np.ndarray, target_freq: float, df: float, background: float) -> float` | MSB-SE 切片 SNR 计算 |
| `_get_slice_value` | `_get_slice_value(msb_se_slice: np.ndarray, fc_axis: np.ndarray, target_freq: float, df: float) -> float` | MSB-SE 切片峰值提取 |

### `_compute_slice_snr`

```python
def _compute_slice_snr(
    msb_se_slice: np.ndarray,
    fc_axis: np.ndarray,
    target_freq: float,
    df: float,
    background: float,
) -> float
```

- **参数**:
  - `msb_se_slice` (`np.ndarray`): MSB-SE 切片幅值
  - `fc_axis` (`np.ndarray`): 切片频率轴（Hz）
  - `target_freq` (`float`): 目标特征频率（Hz）
  - `df` (`float`): 频率分辨率（Hz）
  - `background` (`float`): 背景中位数
- **返回值**：`float` — 目标频率处峰值与背景的比值（SNR）
- **说明**：在 MSB-SE 切片指定频率附近 ±3·df 范围内搜索峰值，与背景比较得到 SNR。

### `_get_slice_value`

```python
def _get_slice_value(
    msb_se_slice: np.ndarray,
    fc_axis: np.ndarray,
    target_freq: float,
    df: float,
) -> float
```

- **参数**:
  - `msb_se_slice` (`np.ndarray`): MSB-SE 切片幅值
  - `fc_axis` (`np.ndarray`): 切片频率轴（Hz）
  - `target_freq` (`float`): 目标特征频率（Hz）
  - `df` (`float`): 频率分辨率（Hz）
- **返回值**：`float` — 目标频率处峰值幅值
- **说明**：在 MSB-SE 切片指定频率附近 ±3·df 范围内搜索最大幅值。
