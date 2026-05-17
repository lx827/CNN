# `core.py` — 设备 CRUD

**对应源码**：`cloud/app/api/devices/core.py`

## 路由端点

### `GET /api/devices/`

```python
@router.get("/")
def get_devices(db: Session = Depends(get_db)) -> dict
```

- **响应**：`{code, data: [{id, device_id, name, location, channel_count, channel_names, sample_rate, window_seconds, health_score, status, runtime_hours, upload_interval, task_poll_interval, alarm_thresholds, gear_teeth, bearing_params, compression_enabled, downsample_ratio, is_online, last_seen_at}]}`
- **说明**：所有设备列表（含全部字段）
