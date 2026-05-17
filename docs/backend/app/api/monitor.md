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

## 内部函数

### `_get_channel_name`

```python
def _get_channel_name(device: Device, channel_num: int) -> str
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `device` | `Device` | 设备实例（可为 `None`） |
| `channel_num` | `int` | 通道编号 |

- **返回值**：`str` — 通道显示名称
- **说明**：从设备配置的 `channel_names` 中查找通道名称；未配置时返回默认名称（1→"通道1-轴承附近"、2→"通道2-驱动端"、3→"通道3-风扇端"，其余返回"通道{N}"）
