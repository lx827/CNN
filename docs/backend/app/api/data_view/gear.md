# `gear.py` — 齿轮诊断+综合分析+全分析

**对应源码**：`cloud/app/api/data_view/gear.py`

## 函数

### `_extract_device_param`

```python
def _extract_device_param(params, device_keys) -> dict
```

- **说明**：兼容前端通道级格式与后端设备级格式转换

### `_has_valid_bearing`

```python
def _has_valid_bearing(bp) -> bool
```

- **说明**：轴承参数有效性（n,d,D 均>0）

### `_has_valid_gear`

```python
def _has_valid_gear(gt) -> bool
```

- **说明**：齿轮参数有效性（input>0）

## 路由端点

### `GET /{device_id}/{batch_index}/{channel}/gear`

```python
@router.get("/{device_id}/{batch_index}/{channel}/gear")
async def get_channel_gear(
    device_id: str, batch_index: int, channel: int,
    detrend: bool = Query(default=False),
    method: str = Query(default="standard"),
    denoise: str = Query(default="none"),
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **响应 data**：`{rot_freq_hz, mesh_freq_hz, mesh_order, ser, sidebands, fm0, fm4, car, m6a, m8a, fault_indicators}`
- **说明**：齿轮诊断

### `GET /{device_id}/{batch_index}/{channel}/analyze`

```python
@router.get("/{device_id}/{batch_index}/{channel}/analyze")
async def get_channel_analyze(
    device_id: str, batch_index: int, channel: int,
    detrend: bool = Query(default=False),
    strategy: str = Query(default="standard"),
    bearing_method: str = Query(default="envelope"),
    gear_method: str = Query(default="standard"),
    denoise: str = Query(default="none"),
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **strategy 映射**：standard→runtime, advanced→balanced, expert→exhaustive
- **说明**：综合故障诊断统一入口。自动写入 `Diagnosis.engine_result`

### `GET /{device_id}/{batch_index}/{channel}/full-analysis`

```python
@router.get("/{device_id}/{batch_index}/{channel}/full-analysis")
async def get_channel_full_analysis(
    device_id: str, batch_index: int, channel: int,
    detrend: bool = Query(default=False),
    denoise: str = Query(default="none"),
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **说明**：全算法对比分析。自动写入 `Diagnosis.full_analysis`
