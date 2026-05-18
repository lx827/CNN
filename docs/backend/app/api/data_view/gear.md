# `gear.py` — 齿轮诊断+综合分析+全分析

> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/api/data_view/gear.py`

## 函数

> `_extract_device_param` 已统一到 `__init__.py`。本模块通过 `from . import _extract_device_param` 导入。
>
> `_has_valid_bearing` 和 `_has_valid_gear` 现在先调用 `_extract_device_param` 做格式转换，再委托 `app/services/diagnosis/features.py` 中的 `has_bearing_params` / `has_gear_params` 做统一校验。

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
- **说明**：齿轮诊断。返回值通过 `_sanitize_for_json` 包裹，确保 numpy 类型可被 FastAPI 序列化。

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
- **说明**：综合故障诊断统一入口。自动写入 `Diagnosis.engine_result`。返回值通过 `_sanitize_for_json` 包裹。

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
- **说明**：全算法对比分析。自动写入 `Diagnosis.full_analysis`。返回值通过 `_sanitize_for_json` 包裹。
