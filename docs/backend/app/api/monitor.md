# `monitor.py` — 实时监测

**对应源码**：`cloud/app/api/monitor.py` | `prefix=/api/monitor` | `tags=[实时监测]`

## 路由端点

### `GET /api/monitor/latest`

```python
@router.get("/latest")
def get_latest_monitor(
    device_id: str,
    prefer_special: bool = False,
    limit: int = 3,
    db: Session = Depends(get_db)
) -> dict
```

- **响应**：`{code, data: items}` — 每项含 `data`（时域）、`fft_freq`、`fft_amp`、`channel_name`
- **说明**：获取最新监测数据（时域+FFT）

### `GET /api/monitor/history`

```python
@router.get("/history")
def get_monitor_history(
    device_id: str,
    channel: int = 1,
    batches: int = 16,
    include_special: bool = True,
    db: Session = Depends(get_db)
) -> dict
```

- **说明**：获取历史监测数据
