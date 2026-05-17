# `diagnosis_ops.py` — 诊断缓存操作+重新诊断

**对应源码**：`cloud/app/api/data_view/diagnosis_ops.py`

## 函数

### `_sanitize_for_json`

```python
def _sanitize_for_json(obj) -> Any
```

- **说明**：递归将 numpy 类型转换为 Python 原生类型，确保 JSON 可序列化

## 路由端点

### `PUT /{device_id}/{batch_index}/diagnosis`

```python
@router.put("/{device_id}/{batch_index}/diagnosis")
async def update_batch_diagnosis(
    device_id: str, batch_index: int,
    order_analysis: Optional[dict] = Body(default=None),
    rot_freq: Optional[float] = Body(default=None),
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **说明**：更新批次诊断（阶次追踪后写回转频）

### `GET /{device_id}/{batch_index}/{channel}/diagnosis`

```python
@router.get("/{device_id}/{batch_index}/{channel}/diagnosis")
def get_channel_diagnosis(
    device_id: str, batch_index: int, channel: int,
    denoise_method: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
) -> dict
```

- **说明**：查询诊断缓存（优先级：精确匹配 denoise_method → 通道最新 → 批次级）

### `POST /{device_id}/{batch_index}/reanalyze`

```python
@router.post("/{device_id}/{batch_index}/reanalyze")
async def reanalyze_batch(
    device_id: str, batch_index: int,
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **说明**：单批次重新诊断（要求设备在线）

### `POST /{device_id}/reanalyze-all`

```python
@router.post("/{device_id}/reanalyze-all")
async def reanalyze_all_batches(
    device_id: str,
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **响应**：`{code, message, data: {total, updated, errors, results}}`
- **说明**：全部批次重新诊断（逐批次串行，成功即 commit）
