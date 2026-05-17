# `engine.py` — 诊断引擎调度器

**对应源码**：`cloud/app/services/diagnosis/engine.py`

## 枚举

### `DiagnosisStrategy`

| 成员 | 值 | 说明 |
|------|-----|------|
| STANDARD | `"standard"` | 标准分析（包络+FFT+阶次） |
| ADVANCED | `"advanced"` | 高级分析（Kurtogram+CPW+MED） |
| EXPERT | `"expert"` | 专家模式（全算法+决策融合） |

### `BearingMethod`

| 成员 | 值 | 说明 |
|------|-----|------|
| ENVELOPE | `"envelope"` | 标准包络分析 |
| KURTOGRAM | `"kurtogram"` | Fast Kurtogram 自适应包络 |
| CPW | `"cpw"` | CPW 预白化 + 包络 |
| MED | `"med"` | MED 增强 + 包络 |
| TEAGER | `"teager"` | Teager 能量算子 + 包络 |
| SPECTRAL_KURTOSIS | `"spectral_kurtosis"` | 自适应谱峭度重加权包络 |
| SC_SCOH | `"sc_scoh"` | 轴承谱相关/谱相干（循环平稳分析） |
| MCKD | `"mckd"` | 最大相关峭度解卷积 + 包络 |
| WP | `"wp"` | 小波包轴承诊断 |
| DWT | `"dwt"` | DWT敏感层轴承诊断 |
| EMD_ENVELOPE | `"emd_envelope"` | EMD敏感IMF轴承诊断 |
| CEEMDAN_ENVELOPE | `"ceemdan_envelope"` | CEEMDAN敏感IMF轴承诊断 |
| VMD_ENVELOPE | `"vmd_envelope"` | VMD敏感模态轴承诊断 |

### `GearMethod`

| 成员 | 值 | 说明 |
|------|-----|------|
| STANDARD | `"standard"` | 标准边频带分析 + SER |
| ADVANCED | `"advanced"` | FM0/FM4/NA4 + SER + CAR |

### `DenoiseMethod`

| 成员 | 值 | 说明 |
|------|-----|------|
| NONE | `"none"` | 无预处理 |
| WAVELET | `"wavelet"` | 小波阈值去噪 |
| VMD | `"vmd"` | VMD 变分模态分解降噪 |
| WAVELET_VMD | `"wavelet_vmd"` | 小波+VMD 级联 |
| WAVELET_LMS | `"wavelet_lms"` | 小波+LMS 级联 |
| EMD | `"emd"` | 经验模态分解降噪 |
| CEEMDAN | `"ceemdan"` | 完备集成经验模态分解降噪 |
| SAVGOL | `"savgol"` | Savitzky-Golay 多项式平滑 |
| WAVELET_PACKET | `"wavelet_packet"` | 小波包能量阈值降噪 |
| CEEMDAN_WP | `"ceemdan_wp"` | CEEMDAN+小波包级联降噪 |
| EEMD | `"eemd"` | 集成经验模态分解降噪 |

## 类

### `DiagnosisEngine`

```python
class DiagnosisEngine
```

#### `__init__`

```python
def __init__(
    self,
    strategy = DiagnosisStrategy.STANDARD,
    bearing_method = BearingMethod.ENVELOPE,
    gear_method = GearMethod.STANDARD,
    denoise_method = DenoiseMethod.NONE,
    bearing_params: Optional[Dict] = None,
    gear_teeth: Optional[Dict] = None,
)
```

#### `preprocess`

```python
def preprocess(self, signal: np.ndarray) -> np.ndarray
```

- **返回值**：`np.ndarray`
- **说明**：去直流 + 按 `denoise_method` 路由到各去噪函数

#### `_estimate_rot_freq`

```python
def _estimate_rot_freq(self, signal: np.ndarray, fs: float) -> Tuple[float, oa, os_, method, std]
```

- **返回值**：`(rot_freq, order_axis, order_spectrum, tracking_method_str, rot_std)`
- **说明**：多帧估计转频，自动切换 single_frame/multi_frame/varying_speed

#### `analyze_bearing`

```python
def analyze_bearing(
    self,
    signal: np.ndarray,
    fs: float,
    rot_freq: Optional[float] = None,
    preprocess: bool = True,
) -> Dict[str, Any]
```

- **返回值**：`{method, strategy, rot_freq_hz, envelope_freq, envelope_amp, features, fault_indicators}`
- **说明**：轴承诊断入口

#### `analyze_gear`

```python
def analyze_gear(
    self,
    signal: np.ndarray,
    fs: float,
    rot_freq: Optional[float] = None,
    preprocess: bool = True,
    _cached_oa: Optional[np.ndarray] = None,
    _cached_os: Optional[np.ndarray] = None,
) -> Dict[str, Any]
```

- **返回值**：`{method, strategy, rot_freq_hz, mesh_freq_hz, mesh_order, ser, sidebands, fm0, fm4, car, m6a, m8a, fault_indicators, planetary_*}`
- **说明**：齿轮诊断入口。行星箱 Level 2a~2d 默认，Level 3~5 需 `_run_slow_methods=True`

#### `analyze_comprehensive`

```python
def analyze_comprehensive(
    self,
    signal: np.ndarray,
    fs: float,
    rot_freq: Optional[float] = None,
    skip_bearing: bool = False,
    skip_gear: bool = False,
) -> Dict[str, Any]
```

- **说明**：综合分析（轴承+齿轮+时域）
