# `engine.py` — 诊断引擎调度器


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
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

#### `analyze_research_ensemble`

```python
def analyze_research_ensemble(
    self,
    signal: np.ndarray,
    fs: float,
    rot_freq: Optional[float] = None,
    profile: str = "runtime",
    max_seconds: float = 5.0,
) -> Dict[str, Any]
```

| 参数 | 类型 | 说明 |
|------|------|------|
| signal | `np.ndarray` | 输入振动信号 |
| fs | `float` | 采样率（Hz） |
| rot_freq | `Optional[float]` | 已知转频（Hz），None 时自动估计 |
| profile | `str` | 分析配置：`"runtime"`（后台自动诊断，较快）或 `"exhaustive"`（网页手动重算，更完整） |
| max_seconds | `float` | 信号最大处理时长（秒），超长信号自动截断 |

- **返回值**：`Dict[str, Any]` — `run_research_ensemble` 的完整结果，包含健康度、状态、各方法结果、融合结论等
- **说明**：多算法集成诊断入口。根据 `profile` 选择诊断深度，`runtime` 模式跳过部分慢方法以控制耗时，适合后台 worker 定时调用；`exhaustive` 模式运行全部算法，适合前端手动触发

#### `analyze_all_methods`

```python
def analyze_all_methods(
    self,
    signal: np.ndarray,
    fs: float,
    rot_freq: Optional[float] = None,
    skip_bearing: bool = False,
    skip_gear: bool = False,
) -> Dict[str, Any]
```

| 参数 | 类型 | 说明 |
|------|------|------|
| signal | `np.ndarray` | 输入振动信号 |
| fs | `float` | 采样率（Hz） |
| rot_freq | `Optional[float]` | 已知转频（Hz），None 时自动估计 |
| skip_bearing | `bool` | True 时跳过所有轴承方法 |
| skip_gear | `bool` | True 时跳过所有齿轮方法 |

- **返回值**：`Dict[str, Any]` — `{health_score, status, rot_freq_hz, time_features, bearing_results, gear_results, summary, recommendation}`
  - `bearing_results`: 以 `BearingMethod.value` 为 key 的各轴承方法结果
  - `gear_results`: 以 `GearMethod.value` 为 key 的各齿轮方法结果
  - `summary`: 各方法检出结论汇总
- **说明**：全算法对比分析。遍历所有 `BearingMethod` 和 `GearMethod` 枚举成员逐一运行，对比不同算法的诊断结论。综合健康度取默认方法（包络+标准齿轮）与最差结果的融合值，避免单一方法掩盖故障

## 函数

### `_evaluate_bearing_faults_statistical`

```python
def _evaluate_bearing_faults_statistical(freq_arr: np.ndarray, amp_arr: np.ndarray, rot_freq: float) -> Dict[str, Any]
```

| 参数 | 类型 | 说明 |
|------|------|------|
| freq_arr | `np.ndarray` | 包络谱频率数组 |
| amp_arr | `np.ndarray` | 包络谱幅值数组 |
| rot_freq | `float` | 转频（Hz） |

- **返回值**：`Dict[str, Any]` — 各统计指标字典，键包括：
  - `envelope_peak_snr`: 包络谱峰值 SNR
  - `envelope_kurtosis`: 包络谱峭度
  - `moderate_kurtosis`: 中等峭度路径（外圈/球故障兜底）
  - `low_freq_ratio`: 低频能量占比（区分轴频谐波与轴承故障）
  - `high_freq_ratio`: 高频能量比
  - `peak_concentration`: 谱峰集中度（前5峰能量占比）
  - `envelope_crest_factor`: 包络谱峰值因子
- **说明**：无轴承物理参数时的统计诊断路径。基于包络谱全局统计特征评估异常冲击，通过低频能量占比判断是否为旋转谐波主导，避免健康轴承的转频谐波被误报为轴承故障

### `_evaluate_bearing_faults`

```python
def _evaluate_bearing_faults(
    bearing_params: Optional[Dict],
    env_freq: List[float],
    env_amp: List[float],
    rot_freq: float,
    rot_freq_std: float = 0.0,
) -> Dict[str, Any]
```

| 参数 | 类型 | 说明 |
|------|------|------|
| bearing_params | `Optional[Dict]` | 轴承几何参数（`n` 球数、`d` 球径、`D` 节径、`alpha` 接触角），None 时只走统计路径 |
| env_freq | `List[float]` | 包络谱频率列表 |
| env_amp | `List[float]` | 包络谱幅值列表 |
| rot_freq | `float` | 转频（Hz） |
| rot_freq_std | `float` | 转频标准差（Hz），用于变速工况下放宽容差 |

- **返回值**：`Dict[str, Any]` — 故障指示器字典
  - 有参数时：包含 `BPFO`、`BPFI`、`BSF` 的物理匹配结果，以及以 `_stat` 后缀的统计路径结果
  - 无参数时：仅返回统计路径结果
- **说明**：轴承故障评估双路并行入口。**物理参数路径**：根据轴承几何公式计算理论特征频率，在包络谱中搜索匹配峰值及谐波，BPFI 增加边频带验证；**统计路径**：始终计算作为兜底和佐证。两路结果独立并存，通过 `_stat` 后缀区分。转频不确定性（`rot_freq_std`）越大，搜索容差越宽，避免变速工况漏检
