# `signal_utils.py` — 信号工具


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/signal_utils.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `remove_dc` | `remove_dc(signal) -> np.ndarray` | 去直流 |
| `linear_detrend` | `linear_detrend(signal) -> np.ndarray` | 线性去趋势 |
| `prepare_signal` | `prepare_signal(signal, detrend=False) -> np.ndarray` | 信号预处理 |
| `bandpass_filter` | `bandpass_filter(signal, fs, low, high, order=4) -> np.ndarray` | Butterworth 带通 |
| `lowpass_filter` | `lowpass_filter(signal, fs, cutoff, order=4) -> np.ndarray` | Butterworth 低通 |
| `highpass_filter` | `highpass_filter(signal, fs, cutoff, order=4) -> np.ndarray` | Butterworth 高通 |
| `compute_fft_spectrum` | `compute_fft_spectrum(signal, fs) -> Tuple[np.ndarray, np.ndarray]` | FFT 频谱 |
| `compute_power_spectrum` | `compute_power_spectrum(signal, fs) -> Tuple` | 功率谱 |
| `find_peaks_in_spectrum` | `find_peaks_in_spectrum(freq, spectrum, target_freq, tolerance_percent=3.0, min_snr=3.0) -> Tuple` | 频谱峰值搜索 |
| `compute_snr` | `compute_snr(peak_amp, spectrum, method="median") -> float` | 峰值 SNR |
| `kurtosis` | `kurtosis(signal, fisher=False) -> float` | 峭度 |
| `rms` | `rms(signal) -> float` | RMS |
| `peak_value` | `peak_value(signal) -> float` | 峰值 |
| `crest_factor` | `crest_factor(signal) -> float` | 峰值因子 |
| `skewness` | `skewness(signal) -> float` | 偏度 |
| `estimate_rot_freq_spectrum` | `estimate_rot_freq_spectrum(signal, fs) -> float` | 频谱法估计转频 |
| `estimate_rot_freq_autocorr` | `estimate_rot_freq_autocorr(signal, fs) -> float` | 自相关法估计转频 |
| `estimate_rot_freq_envelope` | `estimate_rot_freq_envelope(signal, fs) -> float` | 包络法估计转频 |
| `zoom_fft_analysis` | `zoom_fft_analysis(signal, fs, center_freq, bandwidth, n_fft) -> Tuple` | ZOOM-FFT 细化谱 |
| `_band_energy` | `_band_energy(freq, amp, center, bandwidth) -> float` | 频带能量积分 |

| `parabolic_interpolation` | `parabolic_interpolation(freqs, spectrum, idx) -> float` | 抛物线插值精确定位谱峰频率 |
| `_order_band_energy` | `_order_band_energy(order_axis, spectrum, center_order: float, bandwidth: float) -> float` | 指定阶次带能量 |
| `lowpass_filter_complex` | `lowpass_filter_complex(signal: np.ndarray, fs: float, f_cut: float, order: int = 6) -> np.ndarray` | 复数信号低通滤波 |

### `parabolic_interpolation`

```python
def parabolic_interpolation(freqs, spectrum, idx) -> float
```

- **参数**:
  - `freqs` — 频率轴（数组）
  - `spectrum` — 频谱幅值（数组）
  - `idx` — 峰值索引
- **返回值**：`float` — 插值后的精确峰值频率
- **说明**：利用峰值及其左右相邻三点的抛物线拟合，精确定位谱峰频率，减小 FFT 栅栏效应误差。

### `_order_band_energy`

```python
def _order_band_energy(order_axis, spectrum, center_order: float, bandwidth: float) -> float
```

- **参数**:
  - `order_axis` — 阶次轴（数组）
  - `spectrum` — 阶次谱幅值（数组）
  - `center_order` (`float`): 目标中心阶次
  - `bandwidth` (`float`): 搜索带宽（单边）
- **返回值**：`float` — 指定阶次带内的能量和（幅值平方和）
- **说明**：阶次域能量积分，与 `_band_energy` 对应。

### `lowpass_filter_complex`

```python
def lowpass_filter_complex(
    signal: np.ndarray,
    fs: float,
    f_cut: float,
    order: int = 6,
) -> np.ndarray
```

- **参数**:
  - `signal` (`np.ndarray`): 复数信号（`dtype=complex`）
  - `fs` (`float`): 采样率 Hz
  - `f_cut` (`float`): 截止频率 Hz
  - `order` (`int`, 默认 6): 滤波器阶数
- **返回值**：`np.ndarray` — 滤波后的复数信号
- **说明**：将复数信号分离实部与虚部分别做 Butterworth 低通滤波，再重新组合。用于 ZOOM-FFT 复调制后的信号滤波。
