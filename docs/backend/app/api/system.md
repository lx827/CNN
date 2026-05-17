# `system.py` — 系统日志

**对应源码**：`cloud/app/api/system.py` | `prefix=/api/logs` | `tags=[系统日志]`

## 路由端点

### `GET /api/logs/`

```python
@router.get("/")
def get_logs(lines: int = 200) -> dict
```

- **参数**：`lines: int = 200` — 拉取的日志行数
- **响应**：`{code, data: {logs}}`
- **说明**：获取内存环形缓冲区日志 + journalctl（Linux）
