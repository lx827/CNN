# `schemas.py` — Pydantic 数据模型

**对应源码**：`cloud/app/schemas.py`

## 类

### `ResponseModel`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| code | int | 200 | 状态码 |
| message | str | "success" | 消息 |
| data | Optional[dict] | None | 数据 |

### `LoginRequest`

| 字段 | 类型 | 说明 |
|------|------|------|
| password | str | 登录密码 |

### `TokenResponse`

| 字段 | 类型 | 说明 |
|------|------|------|
| access_token | str | JWT Token |
| token_type | str="bearer" | Token 类型 |

### `DeviceOut`

| 字段 | 类型 | 说明 |
|------|------|------|
| device_id | str | 设备编号 |
| name | str | 设备名称 |
| location | str | 位置 |
| health_score | int | 健康度 |
| status | str | 状态 |
| runtime_hours | int | 运行时长 |

### `IngestData`

| 字段 | 类型 | 说明 |
|------|------|------|
| device_id | str | 设备编号 |
| timestamp | Optional[datetime] | 时间戳 |
| channels | Dict[str, List[float]] | 通道数据 |
| sample_rate | int=1000 | 采样率 |

### `MonitorData`

| 字段 | 类型 | 说明 |
|------|------|------|
| device_id | str | 设备编号 |
| channel | int | 通道号 |
| data | List[float] | 振动数据 |
| sample_rate | int | 采样率 |
| timestamp | datetime | 时间戳 |

### `DiagnosisOut`

| 字段 | 类型 | 说明 |
|------|------|------|
| device_id | str | 设备编号 |
| health_score | int | 健康度 |
| fault_probabilities | Dict[str, float] | 故障概率 |
| imf_energy | Dict[str, float] | IMF 能量 |
| status | str | 状态 |
| analyzed_at | datetime | 分析时间 |

### `AlarmOut`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 告警 ID |
| device_id | str | 设备编号 |
| level | str | 级别 |
| category | str | 类别 |
| title | str | 标题 |
| description | str | 描述 |
| suggestion | str | 建议 |
| is_resolved | int | 是否已处理 |
| created_at | datetime | 创建时间 |

### `AlarmListResponse`

| 字段 | 类型 | 说明 |
|------|------|------|
| total | int | 总数 |
| items | List[AlarmOut] | 告警列表 |

### `Config`

- **说明**：Pydantic 模型全局配置类
- **配置项**：
  - `from_attributes = True` — 允许从 ORM 对象属性自动映射（Pydantic v2 兼容模式）
