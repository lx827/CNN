# `config.py` — 设备配置

**对应源码**：`cloud/app/api/devices/config.py`

## 路由端点

### `GET /api/devices/edge/config`

```python
@router.get("/edge/config")
def get_edge_config(device_id: str, db: Session = Depends(get_db)) -> dict
```

- **响应**：`{device_id, upload_interval, task_poll_interval, sample_rate, window_seconds, channel_count, compression_enabled, downsample_ratio}`
- **说明**：边端拉取配置

### `GET /api/devices/{device_id}/config`

```python
@router.get("/{device_id}/config")
def get_device_config(device_id: str, db: Session = Depends(get_db)) -> dict
```

- **响应**：同上 + `channel_names, gear_teeth, bearing_params`
- **说明**：前端获取设备配置

### `PUT /api/devices/{device_id}/config`

```python
@router.put("/{device_id}/config")
def update_device_config(device_id: str, payload: dict, db: Session = Depends(get_db)) -> dict
```

- **可更新字段**：`upload_interval, task_poll_interval, sample_rate, window_seconds, channel_count, channel_names, gear_teeth, bearing_params, compression_enabled, downsample_ratio`
- **响应**：`{code, message, data: {device_id, updated}}`

### `PUT /api/devices/batch-config`

```python
@router.put("/batch-config")
def update_batch_config(payload: dict, db: Session = Depends(get_db)) -> dict
```

- **响应**：`{code, message, data: {updated_count, updated_fields}}`
- **说明**：批量更新所有设备配置

### `GET /api/devices/{device_id}/alarm-thresholds`

```python
@router.get("/{device_id}/alarm-thresholds")
def get_alarm_thresholds(device_id: str, db: Session = Depends(get_db)) -> dict
```

- **响应**：`{device_id, alarm_thresholds, effective_thresholds}`
- **说明**：获取告警阈值（用户配置 + 生效值回退）

### `PUT /api/devices/{device_id}/alarm-thresholds`

```python
@router.put("/{device_id}/alarm-thresholds")
def update_alarm_thresholds(device_id: str, payload: dict, db: Session = Depends(get_db)) -> dict
```

- **响应**：`{code, message, data}`
- **说明**：更新告警阈值（rms/peak/kurtosis/crest_factor）
