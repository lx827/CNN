# `offline_monitor.py` — 离线监测

**对应源码**：`cloud/app/services/offline_monitor.py`

## 函数

### `_get_offline_threshold`

```python
def _get_offline_threshold(device: Device, now: datetime) -> datetime
```

- **返回值**：`datetime`
- **说明**：根据通信间隔计算离线阈值（最小 5 分钟，最大 10 分钟）

### `_is_device_offline`

```python
def _is_device_offline(device: Optional[Device], now: Optional[datetime] = None) -> bool
```

- **返回值**：`bool`
- **说明**：判断设备是否离线（`is_online` 唯一写者）

### `offline_monitor_worker`

```python
async def offline_monitor_worker() -> None
```

- **说明**：后台协程：每 30s 扫描更新 `is_online`，广播状态变化
