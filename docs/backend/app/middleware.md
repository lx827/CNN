# `middleware.py` — 中间件

**对应源码**：`cloud/app/middleware.py`

## 函数

### `setup_cors`

```python
def setup_cors(app) -> None
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `app` | `FastAPI` | FastAPI 应用实例 |

- **返回值**：`None`
- **说明**：配置 CORS 中间件，允许前端跨域访问（开发环境）

### `setup_static_files`

```python
def setup_static_files(app) -> None
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `app` | `FastAPI` | FastAPI 应用实例 |

- **返回值**：`None`
- **说明**：静态文件挂载（预留）。如需挂载静态文件，可在此配置。
