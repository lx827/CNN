# `channel.py` — 通道级告警

**对应源码**：`cloud/app/services/alarms/channel.py`

## 函数

### `_check_feature_alarms`

```python
def _check_feature_alarms(
    db, device,
    channel: int,
    channel_name: str,
    features: dict,
    batch_index: int = None
) -> list
```

- **返回值**：`list` — 告警列表
- **说明**：检查 RMS/峰值/峭度/峰值因子是否超阈值

### `_check_gear_alarms`

```python
def _check_gear_alarms(
    db, device,
    channel_diagnosis: dict,
    batch_index: int = None
) -> list
```

- **返回值**：`list`
- **说明**：检查 SER/FM0/CAR/边频带数量是否超标
