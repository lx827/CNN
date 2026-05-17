# `features.py` — 特征提取

**对应源码**：`cloud/app/services/diagnosis/features.py`

## 函数

### `compute_time_features`

```python
def compute_time_features(signal: np.ndarray) -> Dict[str, float]
```

- **返回值**：`{peak, rms, mean_abs, kurtosis, skewness, margin, shape_factor, impulse_factor, crest_factor, rms_mad_z, kurtosis_mad_z, ewma_drift, cusum_score}`
- **说明**：时域统计特征 + 动态基线 + CUSUM

### `_compute_dynamic_baseline_features`

```python
def _compute_dynamic_baseline_features(signal: np.ndarray) -> Dict[str, float]
```

- **返回值**：`{rms_mad_z, kurtosis_mad_z, ewma_drift, cusum_score}`
- **说明**：滑动窗口鲁棒基线（MAD z-score + EWMA + CUSUM）

### `compute_fft_features`

```python
def compute_fft_features(
    signal: np.ndarray,
    fs: float,
    gear_teeth: Optional[Dict] = None,
    bearing_params: Optional[Dict] = None,
    rot_freq: Optional[float] = None,
) -> Dict[str, float]
```

- **返回值**：`{estimated_rot_freq, mesh_freq_hz, mesh_freq_ratio, sideband_total_ratio, sideband_count, BPFO_hz, BPFO_ratio, ...}`
- **说明**：FFT 频域特征

### `compute_envelope_features`

```python
def compute_envelope_features(
    envelope_freq: list,
    envelope_amp: list,
    bearing_params: Optional[Dict] = None,
    rot_freq: Optional[float] = None,
) -> Dict[str, float]
```

- **返回值**：`{total_env_energy, BPFO_env_ratio, BPFI_env_ratio, BSF_env_ratio, *_harmonic_ratio}`
- **说明**：包络域特征（基于已有包络谱）

### `remove_dc`

```python
def remove_dc(signal: List[float]) -> np.ndarray
```

- **说明**：去直流+线性去趋势

### `compute_channel_features`

```python
def compute_channel_features(signal: List[float]) -> Dict[str, float]
```

- **返回值**：`{peak, rms, kurtosis, skewness, margin, crest_factor, shape_factor, impulse_factor}`
- **说明**：单通道特征（用于通道级告警）

### `compute_fft`

```python
def compute_fft(signal: List[float], sample_rate: int = 25600) -> Tuple[list, list]
```

- **返回值**：`(freq, amp)`
- **说明**：FFT 频谱

### `compute_imf_energy`

```python
def compute_imf_energy(signal: List[float], sample_rate: int = 25600) -> Dict[str, float]
```

- **返回值**：`{IMF1~5: %}`
- **说明**：IMF 能量分布

### `_compute_bearing_fault_freqs`

```python
def _compute_bearing_fault_freqs(rot_freq: float, bearing_params: dict) -> dict
```

- **返回值**：`{BPFO, BPFI, BSF, FTF}`
- **说明**：轴承故障频率

### `_compute_bearing_fault_orders`

```python
def _compute_bearing_fault_orders(rot_freq: float, bearing_params: dict) -> dict
```

- **返回值**：`{BPFO, BPFI, BSF, FTF}`
- **说明**：轴承故障阶次

### `_sign_cusum`

```python
def _sign_cusum(series: np.ndarray, reference: Optional[float] = None) -> Tuple[float, float, Dict]
```

- **返回值**：`(C⁺_max, C⁻_max, info)`
- **说明**：符号统计非参数 CUSUM

### `_mann_whitney_cusum`

```python
def _mann_whitney_cusum(
    series: np.ndarray,
    window_size: int = 10,
    reference_window: Optional[np.ndarray] = None,
) -> Tuple[float, float, Dict]
```

- **返回值**：`(C⁺_max, C⁻_max, info)`
- **说明**：Mann-Whitney 非参数 CUSUM

### `compute_nonparam_cusum_features`

```python
def compute_nonparam_cusum_features(signal: np.ndarray) -> Dict[str, float]
```

- **返回值**：`{sign_cusum_positive, sign_cusum_negative, sign_cusum_alarm, mw_cusum_positive, mw_cusum_negative, mw_cusum_alarm}`
- **说明**：非参数 CUSUM 特征
