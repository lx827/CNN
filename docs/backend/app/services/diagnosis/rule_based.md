# `rule_based.py` — 规则诊断（回退）


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/rule_based.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `adaptive_rms_baseline` | `adaptive_rms_baseline(rot_freq_hz) -> float` | 自适应 RMS 基线 |
| `_rule_based_analyze` | `_rule_based_analyze(channels_data: Dict[str, List[float]], sample_rate: int = 25600, device=None) -> dict` | 规则诊断主入口（崩溃回退） |
| `compute_envelope_spectrum` | `compute_envelope_spectrum(signal: List[float], sample_rate: int = 25600, max_freq: int = 1000) -> Tuple[List[float], List[float]]` | 包络谱计算 |
| `_extract_spectrum_features` | `_extract_spectrum_features(freq, amp, rot_freq, gear_teeth, bearing_params) -> dict` | 频谱特征提取 |
| `_extract_envelope_features` | `_extract_envelope_features(envelope_freq, envelope_amp, rot_freq, bearing_params) -> dict` | 包络特征提取 |
| `_extract_order_features` | `_extract_order_features(order_axis, spectrum, rot_freq, gear_teeth, bearing_params) -> dict` | 阶次特征提取 |
| `_order_band_energy` | `_order_band_energy(order_axis, spectrum, center_order: float, bandwidth: float) -> float` | 指定阶次带能量和 |
| `_feature_severity` | `_feature_severity(value: float, metric: str, rot_freq: float = 0.0) -> float` | 单一特征严重度 (0.0~1.0+) |
| `_compute_order_spectrum_simple` | `_compute_order_spectrum_simple(sig: np.ndarray, fs: float, rot_freq: float, samples_per_rev: int = 1024, max_order: int = 50) -> Tuple[np.ndarray, np.ndarray]` | 简化阶次跟踪（单帧） |
| `_band_energy` | `_band_energy(freq, amp, center: float, bandwidth: float) -> float` | 指定频带能量积分 |

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
- **说明**：阶次域版 `_band_energy`，用于阶次谱特征提取。

### `_feature_severity`

```python
def _feature_severity(value: float, metric: str, rot_freq: float = 0.0) -> float
```

- **参数**:
  - `value` (`float`): 特征实测值
  - `metric` (`str`): 特征名称（如 `"rms"`, `"kurtosis"`, `"crest_factor"` 等）
  - `rot_freq` (`float`, 默认 0.0): 转频 Hz，用于 RMS 基线自适应
- **返回值**：`float` — 严重度归一化到 0.0~1.0+
- **说明**：基于预设阈值计算单一特征的严重度。RMS 基线随转速自适应：`baseline = max(1.0, 0.05·rot_freq + 1.0)`。

### `_compute_order_spectrum_simple`

```python
def _compute_order_spectrum_simple(
    sig: np.ndarray,
    fs: float,
    rot_freq: float,
    samples_per_rev: int = 1024,
    max_order: int = 50,
) -> Tuple[np.ndarray, np.ndarray]
```

- **参数**:
  - `sig` (`np.ndarray`): 输入信号
  - `fs` (`float`): 采样率 Hz
  - `rot_freq` (`float`): 转频 Hz
  - `samples_per_rev` (`int`, 默认 1024): 每转采样点数
  - `max_order` (`int`, 默认 50): 最大输出阶次
- **返回值**：`(orders, spectrum)` — 阶次轴与阶次谱幅值
- **说明**：简化单帧阶次跟踪。按转频等角度重采样后做 FFT，输出 0~max_order 的阶次谱，供规则诊断内部快速使用。

### `_band_energy`

```python
def _band_energy(freq, amp, center: float, bandwidth: float) -> float
```

- **参数**:
  - `freq` — 频率轴（数组）
  - `amp` — 频谱幅值（数组）
  - `center` (`float`): 频带中心频率
  - `bandwidth` (`float`): 搜索带宽（单边）
- **返回值**：`float` — 指定频带内的能量和（幅值平方和）
- **说明**：频域能量积分，用于频谱特征提取和包络谱分析。

