# `ingest.py` — 边端数据接入

**对应源码**：`cloud/app/api/ingest.py` | `prefix=/api/ingest` | `tags=[数据接入]`

## 常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `MAX_BATCHES_NORMAL` | 16 | 普通数据最多保留批次 |
| `SPECIAL_BATCH_START` | 100 | 特殊数据从 101 起 |

## 函数

### `_decompress_channels`

```python
def _decompress_channels(payload: dict) -> dict
```

- **返回值**：`dict` — 解压后的通道数据
- **说明**：解压 base64+zlib+msgpack/json 数据

### `_get_next_batch_index`

```python
def _get_next_batch_index(db: Session, device_id: str, is_special: bool = False) -> int
```

- **返回值**：`int` — 下一批次号
- **说明**：普通数据 1~16 循环覆盖，特殊数据 101+ 自增永不覆盖

## 路由端点

### `POST /api/ingest/`

```python
@router.post("/")
def ingest_data(payload: dict, db: Session = Depends(get_db)) -> dict
```

- **请求体**：`{device_id, channels/compressed_data, batch_index?, is_special?}`
- **说明**：边端上传传感器数据（支持压缩/原图模式）
