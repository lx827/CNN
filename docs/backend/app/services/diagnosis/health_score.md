# `health_score.py` — 健康度评分


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/health_score.py`

## 常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `CREST_EVIDENCE_THRESHOLD` | `10.0` | 峰值因子证据门控阈值 |
| `DEDUCTION_WEIGHT_MAP` | dict（20+ 项） | 扣分名称 → 权重键映射 |

## 函数

### `_compute_health_score`

```python
def _compute_health_score(
    gear_teeth: Optional[Dict],
    time_features: Dict,
    bearing_result: Dict,
    gear_result: Dict,
    ds_fusion_result: Optional[Dict] = None,
) -> Tuple[int, str, list]
```

- **返回值**：`(health_score, status, deductions)`
- **说明**：综合健康度评分 (0-100)，连续 sigmoid 衰减扣分

**状态判定**：
- health_score ≥ 85 → normal
- 60 ≤ health_score < 85 → warning（若有 critical 或 time_abnormal）否则 normal
- health_score < 60 → fault（若有 critical）否则 warning

### `get_ds_label`

```python
def get_ds_label(ds_fusion_result: Optional[Dict]) -> Optional[str]
```

- **说明**：从 D-S 融合结果提取主导故障标签

### `is_ds_conflict_high`

```python
def is_ds_conflict_high(ds_fusion_result: Optional[Dict]) -> bool
```

- **说明**：判断 D-S 冲突是否过高（conflict > 0.8）

### `_infer_gear_subtype_from_indicators`

```python
def _infer_gear_subtype_from_indicators(gear_result: Dict) -> Optional[str]
```

- **参数**：`gear_result` — `analyze_gear()` 的返回结果，需包含 `fault_indicators`
- **返回值**：`"break" | "crack" | "wear" | "missing" | None`
- **说明**：从 gear fault_indicators 推断具体齿轮故障子类型（planetary gear 专用）。

**判定规则**：

| 故障类型 | 关键指标 | 判定条件 |
|----------|----------|----------|
| missing | `planetary_fullband_env_kurt` | `pfek > 10.0` 且 `ser < 12.0` |
| wear | `fm4` + `pfek` | `fm4 > 3.5` (warning) 且 `pfek > 3.0` |
| break | `fm0` / `ser` / `sideband_count` | `fm0 > 5.0` 或 `ser > 10.0` 或 `sideband_count` 异常 |
| crack | `pfek` + `fm4` | `pfek < 3.0` 且 `fm4 < 4.0` |

- 各类型按证据分累加，最高分 ≥ 1.5 时返回对应子类型
- 用于 `_fault_label()` 和 `infer_gear_label_from_ensemble()` 的故障子类型推断

### `_sf`

```python
def _sf(val, default=0.0)
```

- **参数**:
  - `val` — 输入值（通常为 `None` 或数值）
  - `default` (`float`, 默认 `0.0`): 当 `val` 为 `None` 时的回退值
- **返回值**：`float` — 安全的浮点数值
- **说明**：Safe Float 辅助函数。将 `None` 转换为默认浮点值，防止健康度评分过程中出现 `TypeError`
