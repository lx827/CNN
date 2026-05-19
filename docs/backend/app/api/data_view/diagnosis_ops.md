# `diagnosis_ops.py` — 诊断缓存操作+重新诊断

> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/api/data_view/diagnosis_ops.py`

## 函数

> `_sanitize_for_json` 已统一到 `__init__.py`。本模块通过 `from . import _sanitize_for_json` 导入。

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

- **说明**：查询诊断缓存。查询优先级（2025-05 更新，新增 `order_analysis` 回退）：
  1. 精确匹配 `device + batch + channel + denoise_method` → 返回 `engine_result` 或 `full_analysis`
  2. 同记录 `engine_result`/`full_analysis` 为空 → **回退到 `order_analysis.channels`** 提取该通道结果
  3. 通道级记录（不限去噪）→ 同上两步
  4. 批次级记录 → 优先 `order_analysis.channels` → `order_analysis.engine_result` → 传统批次数据
  - 所有返回值通过 `_sanitize_for_json` 包裹，确保数据库中的旧数据（含 numpy 类型）可被 FastAPI 序列化。
  - **`full_analysis` 字段结构**：包含完整 `run_research_ensemble()` 结果，含 `ensemble`（轴承/齿轮投票、置信度、D-S 融合）、`bearing`、`gear`、`time_features` 等。详见 `ensemble.py`。

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
