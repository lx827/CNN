# `bearing.py` — 轴承诊断算法


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/bearing.py`

## 函数

### `envelope_analysis`

```python
def envelope_analysis(
    signal: np.ndarray,
    fs: float,
    fc: Optional[float] = None,
    bw: Optional[float] = None,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
) -> Dict
```

- **返回值**：`{envelope_freq, envelope_amp, band_center, band_width}`
- **说明**：标准包络分析（带通→Hilbert→低通→FFT）

### `fast_kurtogram`

```python
def fast_kurtogram(
    signal: np.ndarray,
    fs: float,
    max_level: int = 6,
    f_low: float = 100.0,
) -> Dict
```

- **返回值**：`{envelope_freq, envelope_amp, optimal_fc, optimal_bw, max_kurtosis, kurtogram}`
- **说明**：Fast Kurtogram + 最优频带包络

### `cpw_envelope_analysis`

```python
def cpw_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    comb_frequencies: List[float],
    max_freq: float = 1000.0,
) -> Dict
```

- **返回值**：`{envelope_freq, envelope_amp, comb_frequencies, method}`
- **说明**：CPW 预白化 + 包络

### `med_envelope_analysis`

```python
def med_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    med_filter_len: int = 64,
    max_freq: float = 1000.0,
) -> Dict
```

- **返回值**：`{envelope_freq, envelope_amp, med_filter_len, kurtosis_before, kurtosis_after, method}`
- **说明**：MED 增强 + 包络

### `teager_envelope_analysis`

```python
def teager_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    max_freq: float = 1000.0,
) -> Dict
```

- **返回值**：`{envelope_freq, envelope_amp, method, teager_rms}`
- **说明**：TEO + Fast Kurtogram 包络

### `spectral_kurtosis_envelope_analysis`

```python
def spectral_kurtosis_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    max_level: int = 6,
    f_low: float = 100.0,
    max_freq: float = 1000.0,
) -> Dict
```

- **返回值**：`{envelope_freq, envelope_amp, method, optimal_fc, optimal_bw, reweighted_score, spectral_kurtosis_bands}`
- **说明**：自适应谱峭度重加权包络
