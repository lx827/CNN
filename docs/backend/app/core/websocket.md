# `websocket.py` — WebSocket 连接管理器

**对应源码**：`cloud/app/core/websocket.py`

## 类

### `ConnectionManager`

```python
class ConnectionManager
```

| 方法 | 签名 | 说明 |
|------|------|------|
| `__init__` | `__init__()` | 初始化连接列表 `active_connections: List[WebSocket]` |
| `connect` | `async connect(websocket: WebSocket)` | 接受连接并添加到列表 |
| `disconnect` | `disconnect(websocket: WebSocket)` | 从列表中移除 |
| `broadcast` | `async broadcast(message: dict)` | 向所有连接广播 JSON 消息，自动移除断开的连接 |

## 全局变量

| 变量 | 类型 | 说明 |
|------|------|------|
| `manager` | `ConnectionManager()` | 全局单例，整个应用共享 |
