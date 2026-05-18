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

**参数有效性判断已统一到 `features.py`**：

- `has_bearing_params(bearing_params)` — 轴承参数有效性（n, d, D 均 >0）
- `has_gear_params(gear_teeth)` — 齿轮参数有效性（input >0）

ensemble.py 通过 `from .features import has_bearing_params, has_gear_params` 导入统一版本，不再本地定义。

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
- **说明**：齿轮投票置信度

**行星齿轮箱特殊处理**（2025-05）：

- 当 `planet_count >= 3` 时，使用独立阈值：`kurt > 10` 或 `crest > 10` 或 `kurt < 5.5` 打开 impulse gate
- warning hits 给 0.05~0.35 分（根据命中数量和类型），critical hits 给 0.20~0.60 分
- `abnormal = confidence >= 0.55`

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

- **返回值**：`str` — 如 `"gear_break"`、`"gear_crack"`、`"gear_wear"`、`"gear_missing"`、`"gear_abnormal"`、`"bearing_abnormal"`、`"unknown"`
- **说明**：生成综合故障标签

**逻辑**：

1. `gear_score > bearing_score` 且 `gear_score >= 0.55` → 调用 `_infer_gear_subtype_from_indicators(best_gear)` 推断具体子类型
2. `gear_score > bearing_score` 但 `< 0.55` → 仍尝试从 indicators 推断子类型（低 confidence 但有 indicators）
3. 否则检查轴承 indicators → 返回轴承标签
4. 无明确证据 → `"unknown"`

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
