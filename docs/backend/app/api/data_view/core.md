# `core.py` — 设备/批次/原始数据

**对应源码**：`cloud/app/api/data_view/core.py`

## 路由端点

### `GET /api/data/devices`

```python
@router.get("/devices")
def get_all_device_data(db: Session = Depends(get_db)) -> dict
```

- **响应**：`{code, data: [{device_id, device_name, channel_count, channel_names, batches}]}`
- **说明**：所有设备批次列表（IN 查询优化，避免 N+1）

### `GET /api/data/{device_id}/batches`

```python
@router.get("/{device_id}/batches")
def get_device_batches(
    device_id: str,
    include_special: bool = Query(default=True),
    db: Session = Depends(get_db)
) -> dict
```

- **响应**：`{code, data: [{batch_index, created_at, is_special, channel_count, sample_rate, diagnosis_status, health_score}]}`
- **说明**：某设备批次概要

### `GET /api/data/{device_id}/{batch_index}/{channel}`

```python
@router.get("/{device_id}/{batch_index}/{channel}")
def get_channel_data(
    device_id: str,
    batch_index: int,
    channel: int,
    detrend: bool = Query(default=False),
    db: Session = Depends(get_db)
) -> dict
```

- **响应**：`{code, data: {device_id, batch_index, channel, channel_name, sample_rate, data, is_analyzed, is_special, created_at}}`
- **说明**：某通道原始时域数据

### `DELETE /api/data/{device_id}/special`

```python
@router.delete("/{device_id}/special")
def delete_special_batches(device_id: str, db: Session = Depends(get_db)) -> dict
```

- **响应**：`{code, message, data: {deleted_batches}}`
- **说明**：删除某设备所有特殊批次

### `DELETE /api/data/{device_id}/{batch_index}`

```python
@router.delete("/{device_id}/{batch_index}")
def delete_batch(
    device_id: str,
    batch_index: int,
    db: Session = Depends(get_db)
) -> dict
```

- **响应**：`{code, message, data: {device_id, batch_index, deleted_channels, is_special}}`
- **说明**：删除某批次（传感器数据+诊断+告警）
