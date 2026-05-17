# `device.py` — 设备级告警

**对应源码**：`cloud/app/services/alarms/device.py`

## 函数

### `_check_device_alarms`

```python
def _check_device_alarms(
    db, device,
    health_score: int,
    fault_probabilities: dict,
    batch_index: int = None,
    order_analysis: dict = None
) -> list
```

- **返回值**：`list`
- **说明**：健康度<60 触发 critical，<80 触发 warning
