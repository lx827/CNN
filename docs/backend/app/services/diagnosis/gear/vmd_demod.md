# `vmd_demod.py` — VMD 齿轮解调


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/gear/vmd_demod.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `vmd_fixed_axis_demod_analysis` | `vmd_fixed_axis_demod_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | 定轴齿轮 VMD 幅频联合解调 |

| `_analyze_fixed_axis_sidebands` | `_analyze_fixed_axis_sidebands(amp_freq: np.ndarray, amp_spectrum: np.ndarray, freq_freq: np.ndarray, freq_spectrum: np.ndarray, mesh_freq: float, rot_freq: float, fs: float, n_sidebands: int = 6, sideband_bw_hz: float = 2.0) -> Dict` | 定轴齿轮箱边频带检测 |
| `_evaluate_fixed_axis_indicators` | `_evaluate_fixed_axis_indicators(ser: float, significant_count: int, mesh_energy: float, demod_type: str) -> Dict` | 定轴齿轮箱解调谱故障指示器评估 |

### `_analyze_fixed_axis_sidebands`

```python
def _analyze_fixed_axis_sidebands(
    amp_freq: np.ndarray,
    amp_spectrum: np.ndarray,
    freq_freq: np.ndarray,
    freq_spectrum: np.ndarray,
    mesh_freq: float,
    rot_freq: float,
    fs: float,
    n_sidebands: int = 6,
    sideband_bw_hz: float = 2.0,
) -> Dict
```

- **参数**:
  - `amp_freq` (`np.ndarray`): 包络谱频率轴
  - `amp_spectrum` (`np.ndarray`): 包络谱幅值
  - `freq_freq` (`np.ndarray`): 频率解调谱频率轴
  - `freq_spectrum` (`np.ndarray`): 频率解调谱幅值
  - `mesh_freq` (`float`): 啮合频率 Hz
  - `rot_freq` (`float`): 转频 Hz
  - `fs` (`float`): 采样率 Hz
  - `n_sidebands` (`int`, 默认 6): 搜索边频带阶数
  - `sideband_bw_hz` (`float`, 默认 2.0): 边频搜索带宽 Hz
- **返回值**：`Dict` — 包含 `amplitude_sidebands`, `frequency_sidebands`, `amplitude_ser`, `frequency_ser`, 及各故障指示器
- **说明**：在幅值解调谱（AM）和频率解调谱（FM）中搜索 `mesh_freq ± n·rot_freq` 边频带，计算 SER 边频能量比和显著边频数，并评估定轴齿轮故障指示器。

### `_evaluate_fixed_axis_indicators`

```python
def _evaluate_fixed_axis_indicators(
    ser: float,
    significant_count: int,
    mesh_energy: float,
    demod_type: str,
) -> Dict
```

- **参数**:
  - `ser` (`float`): 边频能量比
  - `significant_count` (`int`): 显著边频数量
  - `mesh_energy` (`float`): 啮合频率处能量
  - `demod_type` (`str`): 解调类型， `"amplitude"` 或 `"frequency"`
- **返回值**：`Dict` — `{"ser": {...}, "sideband_count": {...}, "demod_type": str}`
- **说明**：根据定轴齿轮箱阈值评估解调谱故障指示器。SER < 1.5 正常，1.5~3.0 warning，> 3.0 critical；显著边频数 ≥ 2 为 warning，≥ 4 为 critical。
