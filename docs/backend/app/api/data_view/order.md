# `order.py` — 阶次跟踪

**对应源码**：`cloud/app/api/data_view/order.py`

## 路由端点

### `GET /{device_id}/{batch_index}/{channel}/order`

```python
@router.get("/{device_id}/{batch_index}/{channel}/order")
async def get_channel_order(
    device_id: str,
    batch_index: int,
    channel: int,
    freq_min: float = Query(default=10.0, ge=1.0, le=500.0),
    freq_max: float = Query(default=100.0, ge=1.0, le=500.0),
    samples_per_rev: int = Query(default=1024, ge=64, le=4096),
    max_order: int = Query(default=50, ge=5, le=200),
    rot_freq: Optional[float] = Query(default=None, ge=1.0, le=500.0),
    detrend: bool = Query(default=False),
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **响应 data**：`{device_id, batch_index, channel, channel_name, sample_rate, is_special, rot_freq, rot_rpm, rot_freq_std, tracking_method, samples_per_rev, orders, spectrum}`
- **说明**：阶次跟踪谱

**跟踪策略自动切换**：
1. `rot_freq` 传入 → 单帧阶次跟踪
2. 多帧估计 → 变异系数 ≤10% → 多帧平均
3. 变异系数 >10% → 变速阶次跟踪（STFT + 等相位重采样）

**自动将转频写入 diagnosis 表**作为后续诊断的权威值。
