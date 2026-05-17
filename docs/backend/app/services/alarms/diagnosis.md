# `diagnosis.py` — 诊断结果告警


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
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
