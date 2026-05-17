# `memory_log.py` — 内存日志

**对应源码**：`cloud/app/core/memory_log.py`

## 类

### `RingBufferHandler`

```python
class RingBufferHandler(logging.Handler)
```

| 方法 | 签名 | 说明 |
|------|------|------|
| `__init__` | `__init__(capacity=2000)` | 环形缓冲区，容量 2000 |
| `emit` | `emit(record: LogRecord)` | 格式化并追加日志 |
| `get_logs` | `get_logs(lines=200) -> str` | 获取最近 N 条日志 |
| `clear` | `clear() -> None` | 清空缓冲区 |

## 函数

### `setup_memory_logging`

```python
def setup_memory_logging(capacity: int = 2000, level: int = logging.INFO) -> None
```

- **说明**：初始化内存日志捕获，挂载 RingBufferHandler 到 root logger，重定向 stdout

### `get_memory_logs`

```python
def get_memory_logs(lines: int = 200) -> str
```

- **返回值**：`str` — 最近 N 条日志文本
- **说明**：获取内存日志

### `get_ring_handler`

```python
def get_ring_handler() -> RingBufferHandler
```

- **返回值**：`RingBufferHandler` — 全局实例
- **说明**：返回全局 handler 实例
