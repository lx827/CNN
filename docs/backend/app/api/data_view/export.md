# `export.py` — CSV 导出

**对应源码**：`cloud/app/api/data_view/export.py`

## 路由端点

### `GET /{device_id}/{batch_index}/{channel}/export`

```python
@router.get("/{device_id}/{batch_index}/{channel}/export")
def export_channel_csv(
    device_id: str, batch_index: int, channel: int,
    detrend: bool = Query(default=False),
    db: Session = Depends(get_db)
) -> StreamingResponse
```

- **响应**：`StreamingResponse`（`text/csv; charset=utf-8-sig`，`Content-Disposition` 附件头）
- **说明**：导出通道数据为 CSV 文件
