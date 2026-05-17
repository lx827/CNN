# `planetary_demod.py` — 行星齿轮解调


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/gear/planetary_demod.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `planetary_envelope_order_analysis` | `planetary_envelope_order_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | 窄带包络阶次分析（Level 2a） |
| `planetary_fullband_envelope_order_analysis` | `planetary_fullband_envelope_order_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | 全频带包络阶次分析（Level 2b） |
| `planetary_tsa_envelope_analysis` | `planetary_tsa_envelope_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | TSA 残差包络阶次分析（Level 2c，区分力=3.31） |
| `planetary_hp_envelope_order_analysis` | `planetary_hp_envelope_order_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | 高通滤波包络阶次分析（Level 2d） |
| `planetary_vmd_demod_analysis` | `planetary_vmd_demod_analysis(signal, fs, rot_freq, gear_teeth, max_K=5) -> dict` | VMD 幅频联合解调（Level 3，慢方法） |
| `planetary_sc_scoh_analysis` | `planetary_sc_scoh_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | 谱相关/谱相干解调（Level 4，慢方法） |
| `planetary_msb_analysis` | `planetary_msb_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | MSB 残余边频带分析（Level 5，慢方法） |
| `evaluate_planetary_demod_results` | `evaluate_planetary_demod_results(narrowband_result, vmd_result) -> dict` | 行星箱结果评估统一入口 |

| `_local_background` | `_local_background(oa, os, center, half_bw=0.5, side_bw=1.5)` | 局部背景估计（阶次谱 SNR 用） |
| `_band_median_background` | `_band_median_background(oa, os, max_order=5.0)` | 频带内中位数背景 |
| `_envelope_order_spectrum` | `_envelope_order_spectrum(signal: np.ndarray, fs: float, rot_freq: float) -> Tuple[np.ndarray, np.ndarray]` | Hilbert 包络 → 阶次谱 |
| `planetary_cvs_med_analysis` | `planetary_cvs_med_analysis(signal: np.ndarray, fs: float, rot_freq: float, gear_teeth: Dict) -> Dict` | CVS+MED 行星轮故障分析 |

### `_local_background`

```python
def _local_background(oa, os, center, half_bw=0.5, side_bw=1.5)
```

- **参数**:
  - `oa` — 阶次轴（数组）
  - `os` — 阶次谱幅值（数组）
  - `center` — 目标阶次中心
  - `half_bw` (`float`, 默认 0.5): 中心排除半带宽
  - `side_bw` (`float`, 默认 1.5): 两侧背景带宽
- **返回值**：`float` — 局部背景幅值均值
- **说明**：用目标阶次两侧 `[center-half_bw-side_bw, center-half_bw]` 与 `[center+half_bw, center+half_bw+side_bw]` 范围内的幅值均值作为局部背景，避免窄带滤波后高频区域无能量导致的 SNR 虚高。

### `_band_median_background`

```python
def _band_median_background(oa, os, max_order=5.0)
```

- **参数**:
  - `oa` — 阶次轴（数组）
  - `os` — 阶次谱幅值（数组）
  - `max_order` (`float`, 默认 5.0): 计算背景的最大阶次上限
- **返回值**：`float` — 0.5~max_order 阶范围内的幅值中位数
- **说明**：对阶次谱在低频段取中位数作为背景，适用于窄带滤波后高阶次区域几乎无能量的场景。

### `_envelope_order_spectrum`

```python
def _envelope_order_spectrum(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
) -> Tuple[np.ndarray, np.ndarray]
```

- **参数**:
  - `signal` (`np.ndarray`): 输入振动信号
  - `fs` (`float`): 采样率 Hz
  - `rot_freq` (`float`): 估计转频 Hz
- **返回值**：`(order_axis, envelope_order_spectrum)` — 阶次轴与包络阶次谱幅值
- **说明**：对信号做 Hilbert 变换提取包络，去直流后对包络信号做阶次谱分析，用于行星齿轮箱故障阶次检测。

### `planetary_cvs_med_analysis`

```python
def planetary_cvs_med_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict
```

- **参数**:
  - `signal` (`np.ndarray`): 原始振动信号
  - `fs` (`float`): 采样率 Hz
  - `rot_freq` (`float`): 估计转频 Hz
  - `gear_teeth` (`Dict`): 齿轮参数 `{sun, ring, planet, planet_count}`
- **返回值**：`Dict` — 包含 `method`, `med_kurtosis`, `envelope_kurtosis`, 各故障阶次 SNR 及显著性标志
- **说明**：Level 5 行星齿轮箱诊断。先利用 carrier 周期进行 CVS（连续振动分离）提取单行星轮啮合段，再执行 MED（最小熵解卷积）增强故障冲击，最后做包络阶次谱分析搜索太阳轮/行星轮故障。
