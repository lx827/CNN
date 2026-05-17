# `recommendation.py` — 诊断建议


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/recommendation.py`

## 函数

### `_match_suggestion`

```python
def _match_suggestion(deductions: list) -> Optional[str]
```

- **说明**：从 SUGGESTION_MAP 匹配最精确建议

### `_generate_recommendation`

```python
def _generate_recommendation(
    bearing_result: Dict,
    gear_result: Dict,
    status: str,
    ds_conflict_high: bool = False,
    deductions: Optional[list] = None,
) -> str
```

- **返回值**：`str` — 诊断建议字符串
- **说明**：生成诊断建议（精确映射 → D-S 冲突 → 条件分支 → 兜底）

### `_generate_recommendation_all`

```python
def _generate_recommendation_all(
    bearing_results: Dict,
    gear_results: Dict,
    status: str,
) -> str
```

- **说明**：基于所有方法结果生成建议

### `_summarize_all_methods`

```python
def _summarize_all_methods(
    bearing_results: Dict,
    gear_results: Dict,
) -> Dict[str, Any]
```

- **返回值**：`{bearing_detections, gear_detections}`
- **说明**：汇总所有方法的检出结论
