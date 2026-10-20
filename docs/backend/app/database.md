# `database.py` — 数据库连接

**对应源码**：`cloud/app/database.py`

**2026-10-21 索引迁移**：`init_db()` 在旧库列迁移完成后，对 Diagnosis 模型的索引逐个 `create(checkfirst=True)`，补齐 `create_all` 不会为已存在表创建的索引。可重复执行，不删表、不修改既有数据；启动期间首次建索引可能增加启动耗时。数据库表结构变更为增量操作，Git 回退代码不会自动删除已建索引。

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

- **参数**：无
- **返回值**：`None`
- **说明**：创建所有表（若不存在）并执行 ALTER TABLE 迁移新增列。自动迁移的列包括：`gear_teeth`、`bearing_params`（Device 表）；`order_analysis`、`rot_freq`、`channel`、`engine_result`、`full_analysis`、`denoise_method`（Diagnosis 表）；`compression_enabled`、`downsample_ratio`、`is_online`（Device 表）。
