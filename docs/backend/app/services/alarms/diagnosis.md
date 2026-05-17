# `diagnosis.py` — 诊断结果告警

**对应源码**：`cloud/app/services/alarms/diagnosis.py`

## 函数

### `_check_diagnosis_alarms`

```python
def _check_diagnosis_alarms(
    db, device,
    fault_probabilities: dict,
    batch_index: int = None
) -> list
```

- **返回值**：`list`
- **说明**：概率>60% 触发 critical，>30% 触发 warning
