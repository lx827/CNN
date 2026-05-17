# `ensemble.py` — 多算法集成诊断


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/ensemble.py`

## 函数

### `_as_float`

```python
def _as_float(value: Any, default: float = 0.0) -> float
```

- **说明**：安全浮点转换

### `_safe_denoise`

```python
def _safe_denoise(value: str) -> DenoiseMethod
```

- **说明**：安全解析去噪方法枚举

### `_profile_config`

```python
def _profile_config(profile: str, denoise_method: str) -> Dict[str, list]
```

- **返回值**：`{denoise: list, bearing: list, gear: list}`
- **说明**：返回 profile 对应的方法列表

**profile 配置**：
| profile | 去噪数 | 轴承方法 | 齿轮方法 |
|---------|--------|---------|---------|
| runtime | 1 | 4（envelope/kurtogram/cpw/teager） | 1（advanced） |
| balanced | 1~2 | 8 | 1 |
| exhaustive | 11（全部） | 13（全部） | 2 |

### `_has_gear_params`

```python
def _has_gear_params(gear_teeth: Optional[Dict]) -> bool
```

- **说明**：`input>0`

### `_has_bearing_params`

```python
def _has_bearing_params(bearing_params: Optional[Dict]) -> bool
```

- **说明**：`n,d,D` 均>0

### `_bearing_confidence`

```python
def _bearing_confidence(result: Dict, time_features: Dict) -> Dict[str, Any]
```

- **返回值**：`{confidence, param_hits, stat_hits, strongest_snr, hits, abnormal}`
- **说明**：轴承投票置信度（impulse_context 门控：kurt>5 或 crest>10）

### `_gear_confidence`

```python
def _gear_confidence(result: Dict, has_gear_params: bool, time_features: Optional[Dict] = None) -> Dict[str, Any]
```

- **返回值**：`{confidence, warning_hits, critical_hits, hits, abnormal}`
- **说明**：齿轮投票置信度（kurt>12 或 crest>12 门控）

### `_time_confidence`

```python
def _time_confidence(time_features: Dict) -> float
```

- **返回值**：`float`
- **说明**：时域冲击证据置信度

### `_fault_label`

```python
def _fault_label(best_bearing: Dict, best_gear: Dict, bearing_score: float, gear_score: float) -> str
```

- **返回值**：`str`
- **说明**：生成综合故障标签

### `run_research_ensemble`

```python
def run_research_ensemble(
    signal: np.ndarray,
    fs: float,
    bearing_params: Optional[Dict] = None,
    gear_teeth: Optional[Dict] = None,
    denoise_method: str = "none",
    rot_freq: Optional[float] = None,
    profile: str = "runtime",
    max_seconds: float = 5.0,
) -> Dict[str, Any]
```

- **返回值**：`{health_score, status, fault_likelihood, fault_label, rot_freq_hz, time_features, bearing, gear, bearing_results, gear_results, ensemble, recommendation}`
- **说明**：集成诊断主入口

**skip 逻辑**：
- 仅配置轴承 → `skip_gear=True`
- 仅配置齿轮 → `skip_bearing=True`
- 都未配置 → 跑统计指标
- 都配置 → 综合全跑
