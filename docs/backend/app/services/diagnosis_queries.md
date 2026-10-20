# `diagnosis_queries.py` — 诊断摘要读模型

对应源码：`cloud/app/services/diagnosis_queries.py`。

## `latest_diagnosis_summaries(db, device_ids, *, per_batch=False)`

- `db`：当前请求的 SQLAlchemy Session；函数不提交或关闭会话。
- `device_ids`：设备编号集合；为空时直接返回空列表。
- `per_batch=False`：每设备一条；为 True 时每个设备批次一条。
- 返回 SQLAlchemy Row 列表，字段为 `device_id, batch_index, health_score, status, fault_probabilities, analyzed_at`。
- 数据库内使用关联 EXISTS 过滤最新记录，按 `analyzed_at`、`id` 降序决定结果；有效时间晚于空时间，同时间用较大的 id 打破并列。
- 不读取 `order_analysis / engine_result / full_analysis`，避免列表请求加载历史算法大对象。
- 调用方：Dashboard、全部设备批次列表、单设备批次列表。保持既有“所有诊断类型中取最新”的规则，不改成仅批次级诊断。
- 由 `ix_diagnosis_device_time`、`ix_diagnosis_batch_time` 支持检索；不依赖数据库窗口函数。
