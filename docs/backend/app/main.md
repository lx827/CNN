# `main.py` — FastAPI 应用入口

**对应源码**：`cloud/app/main.py`

## 函数

### `websocket_endpoint`

```python
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")) -> None
```

- **参数**：
  - `websocket: WebSocket` — WebSocket 连接对象
  - `token: str = Query(default="")` — 查询参数中的认证 token
- **返回值**：`None`
- **说明**：WebSocket 实时推送端点 `/ws/monitor`，验证 token 后建立连接，保持心跳（回复 `{"type":"pong"}`）

### `root`

```python
def root() -> dict
```

- **参数**：无
- **返回值**：`dict` — `{"message": "...", "docs": "/docs"}`
- **说明**：根路径 `/` 健康检查

## 路由注册顺序

1. `auth.router` — 无需认证
2. `ingest.router` — `dependencies=[Depends(optional_auth)]`
3. `dashboard`, `monitor`, `alarms`, `devices`, `data_view`, `collect`, `system` — 均需 `optional_auth`
