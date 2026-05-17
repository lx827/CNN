# `models.py` — SQLAlchemy 数据模型

**对应源码**：`cloud/app/models.py`

## 类

### `Device` — 设备信息表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| device_id | str | 设备编号 |
| name | str | 设备名称 |
| location | str | 位置描述 |
| channel_count | int | 通道数 |
| channel_names | dict | 通道名称映射 |
| sample_rate | int | 采样率 |
| window_seconds | int | 采集窗口秒数 |
| health_score | int | 健康度 0-100 |
| status | str | 状态 |
| runtime_hours | int | 运行时长 |
| upload_interval | int | 上传间隔 |
| task_poll_interval | int | 任务轮询间隔 |
| alarm_thresholds | dict | 告警阈值配置 |
| gear_teeth | dict | 齿轮参数 |
| bearing_params | dict | 轴承参数 |
| compression_enabled | int | 压缩开关 |
| downsample_ratio | int | 降采样比 |
| is_online | bool | 是否在线 |
| last_seen_at | datetime | 最后在线时间 |
| created_at | datetime | 创建时间 |

### `SensorData` — 传感器原始数据表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| device_id | str | 设备编号 |
| batch_index | int | 批次号 |
| channel | int | 通道号 |
| data | list | 振动数据 |
| sample_rate | int | 采样率 |
| is_analyzed | bool | 是否已分析 |
| is_special | bool | 是否特殊采集 |
| analyzed_at | datetime | 分析时间 |
| created_at | datetime | 创建时间 |

### `Diagnosis` — 诊断结果表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| device_id | str | 设备编号 |
| batch_index | int | 批次号 |
| channel | int | 通道号 |
| health_score | int | 健康度 |
| fault_probabilities | dict | 故障概率 |
| imf_energy | dict | IMF 能量 |
| order_analysis | dict | 阶次分析 |
| rot_freq | float | 转频 |
| status | str | 状态 |
| engine_result | dict | 综合分析结果 |
| full_analysis | dict | 全分析结果 |
| denoise_method | str | 去噪方法 |
| analyzed_at | datetime | 分析时间 |

### `Alarm` — 告警记录表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| device_id | str | 设备编号 |
| level | str | 级别（warning/critical） |
| category | str | 类别 |
| channel | int | 通道号 |
| channel_name | str | 通道名称 |
| title | str | 标题 |
| description | str | 描述 |
| suggestion | str | 建议 |
| batch_index | int | 批次号 |
| is_resolved | bool | 是否已处理 |
| created_at | datetime | 创建时间 |
| resolved_at | datetime | 处理时间 |

### `CollectionTask` — 采集任务表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| device_id | str | 设备编号 |
| status | str | 状态（pending/processing/completed） |
| sample_rate | int | 采样率 |
| duration | int | 采集时长 |
| created_at | datetime | 创建时间 |
| started_at | datetime | 开始时间 |
| completed_at | datetime | 完成时间 |
| result_batch_index | int | 结果批次号 |
| error_message | str | 错误信息 |
