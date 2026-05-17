# `research.py` — 研究级分析

**对应源码**：`cloud/app/api/data_view/research.py`

## 常量

| 常量 | 类型 | 说明 |
|------|------|------|
| `METHOD_INFO` | dict | 26+ 种分析方法的元数据（category, label, description） |

## 函数

### `_save_research_diagnosis`

```python
def _save_research_diagnosis(db, device_id, batch_index, channel, denoise, result) -> None
```

- **说明**：将研究诊断结果写入 diagnosis 表缓存

## 路由端点

### `GET /api/data/method-info`

```python
@router.get("/method-info")
async def get_method_info() -> dict
```

- **响应**：`{code, data: METHOD_INFO}`
- **说明**：返回所有可用分析方法信息

### `GET /{device_id}/{batch_index}/{channel}/method-analysis`

```python
@router.get("/{device_id}/{batch_index}/{channel}/method-analysis")
async def get_channel_method_analysis(
    device_id: str, batch_index: int, channel: int,
    method: str = Query(default="all"),
    denoise: str = Query(default="none"),
    detrend: bool = Query(default=False),
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **method 可选值**：轴承 13 种 + 齿轮 2 种 + 行星箱 7 种
- **说明**：单方法/全部方法分析

### `GET /{device_id}/{batch_index}/{channel}/research-analysis`

```python
@router.get("/{device_id}/{batch_index}/{channel}/research-analysis")
async def get_channel_research_analysis(
    device_id: str, batch_index: int, channel: int,
    detrend: bool = Query(default=False),
    profile: str = Query(default="balanced"),
    denoise: str = Query(default="none"),
    max_seconds: float = Query(default=5.0, ge=1.0, le=10.0),
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **说明**：多算法集成研究诊断
