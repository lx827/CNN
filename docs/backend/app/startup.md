# `startup.py` — 数据库初始化

**对应源码**：`cloud/app/startup.py`

## 常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `CW_BEARING_PARAMS` | `{"n": 9, "d": 7.94, "D": 39.04, "alpha": 0}` | CW 轴承参数（ER-16K） |
| `WTGEAR_GEAR_TEETH` | `{"sun": 28, "ring": 100, "planet": 36, "planet_count": 4, "input": 28}` | WTgearbox 行星齿轮参数 |

## 函数

### `init_database`

```python
def init_database() -> None
```

- **说明**：初始化数据库表结构

### `create_initial_devices`

```python
def create_initial_devices() -> None
```

- **说明**：插入 10 台默认设备（WTG-001~010），按数据集分配机械参数
