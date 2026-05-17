# `__init__.py` — 统一入口

**对应源码**：`cloud/app/services/alarms/__init__.py`

## 函数

### `_get_threshold`

```python
def _get_threshold(device: Device, metric: str, level: str) -> float
```

- **返回值**：`float`
- **说明**：读取设备阈值，未配置用默认值，显式置空返回极大值禁用

### `_has_recent_unresolved_alarm`

```python
def _has_recent_unresolved_alarm(
    db: Session,
    device_id: str,
    category: str,
    level: str,
    channel: int = None,
    hours: int = 1
) -> bool
```

- **返回值**：`bool`
- **说明**：检查最近 N 小时内是否已有同类未处理告警

### `generate_alarms`

```python
def generate_alarms(
    db: Session,
    device_id: str,
    health_score: int,
    fault_probabilities: dict,
    channel_features: dict = None,
    batch_index: int = None,
    order_analysis: dict = None,
    channel_diagnosis: dict = None
) -> list
```

- **返回值**：`list` — 生成的告警列表
- **说明**：综合告警生成入口，依次调用四类告警检查，WebSocket 推送新告警
