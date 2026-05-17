# `database.py` — 数据库连接

**对应源码**：`cloud/app/database.py`

## 全局变量

| 变量 | 类型 | 说明 |
|------|------|------|
| `engine` | SQLAlchemy Engine | 数据库引擎（SQLite 或 MySQL） |
| `SessionLocal` | sessionmaker | 会话工厂 |
| `Base` | declarative_base | ORM 基类 |

## 函数

### `get_db`

```python
def get_db() -> Generator
```

- **返回值**：`Generator[Session]`
- **说明**：FastAPI 依赖注入，yield db 后自动 close

### `init_db`

```python
def init_db() -> None
```

- **说明**：创建所有表 + ALTER TABLE 迁移（新增 gear_teeth、bearing_params、channel、engine_result、full_analysis、denoise_method、compression_enabled、downsample_ratio、is_online 等列）
