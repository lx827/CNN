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
- **2026-10-21**：移除额外读取完整波形的无效查询；诊断只读取 `rot_freq` 一列。保留原有批次选择：默认取最大 `batch_index`，`prefer_special=True` 优先取特殊批次，不改变历史数据语义。`limit` 参数保留兼容，当前不裁剪通道。

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
- **查询开销**：先查询批次号，再用 IN 批量读取通道数据；有结果时两次 SELECT，空结果时一次。顺序仍按 `batch_index` 降序，不改为时间排序。

## 内部函数

> `_get_channel_name` 已统一到 `app/api/data_view/__init__.py`。本模块通过 `from app.api.data_view import _get_channel_name` 导入。
