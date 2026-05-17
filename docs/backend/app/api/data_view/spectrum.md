# `spectrum.py` — FFT/STFT/统计

**对应源码**：`cloud/app/api/data_view/spectrum.py`

## 路由端点

### `GET /{device_id}/{batch_index}/{channel}/fft`

```python
@router.get("/{device_id}/{batch_index}/{channel}/fft")
def get_channel_fft(
    device_id: str,
    batch_index: int,
    channel: int,
    max_freq: Optional[int] = 5000,
    detrend: bool = Query(default=False),
    db: Session = Depends(get_db)
) -> dict
```

- **响应 data**：`{device_id, batch_index, channel, channel_name, sample_rate, is_special, fft_freq, fft_amp}`
- **说明**：实时 FFT 频谱

### `GET /{device_id}/{batch_index}/{channel}/stft`

```python
@router.get("/{device_id}/{batch_index}/{channel}/stft")
async def get_channel_stft(
    device_id: str,
    batch_index: int,
    channel: int,
    max_freq: Optional[int] = 5000,
    nperseg: int = Query(default=512, ge=64, le=4096),
    noverlap: int = Query(default=256, ge=0, le=4095),
    detrend: bool = Query(default=False),
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **响应 data**：`{device_id, batch_index, channel, channel_name, sample_rate, is_special, time, freq, magnitude}`
- **说明**：STFT 时频谱（信号截断 5 秒）

### `GET /{device_id}/{batch_index}/{channel}/stats`

```python
@router.get("/{device_id}/{batch_index}/{channel}/stats")
def get_channel_stats(
    device_id: str,
    batch_index: int,
    channel: int,
    window_size: int = Query(default=1024, ge=64, le=8192),
    step: int = Query(default=None, ge=1, le=4096),
    detrend: bool = Query(default=False),
    db: Session = Depends(get_db)
) -> dict
```

- **响应 data**：`{device_id, batch_index, channel, channel_name, sample_rate, peak, rms, kurtosis, skewness, margin, shape_factor, impulse_factor, crest_factor, windowed_kurtosis, window_series, window_params}`
- **说明**：统计特征指标（含加窗时序）
