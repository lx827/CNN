# `health_score.py` — 健康度评分

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
