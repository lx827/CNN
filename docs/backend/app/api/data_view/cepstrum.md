# `cepstrum.py` — 倒谱分析


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/api/data_view/cepstrum.py`

## 路由端点

### `GET /{device_id}/{batch_index}/{channel}/cepstrum`

```python
@router.get("/{device_id}/{batch_index}/{channel}/cepstrum")
async def get_channel_cepstrum(
    device_id: str,
    batch_index: int,
    channel: int,
    max_quefrency: float = Query(default=500.0, ge=10.0, le=2000.0),
    detrend: bool = Query(default=False),
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **响应 data**：`{device_id, batch_index, channel, channel_name, sample_rate, is_special, max_quefrency, quefrency, cepstrum, peaks}`
- **说明**：功率倒谱（加窗 + 对数谱去均值 + 峰值检测）
