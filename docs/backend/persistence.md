# 持久化与诊断缓存契约

ORM 类型以 `cloud/app/models.py` 为准；外部字段见 [API](../api/backend_api.md)。诊断状态、Evidence 和重评语义见 [证据契约](assessment.md)，读写唯一入口为 `services/diagnosis_store.py`。

## 表与所有权

| 表 | 稳定内容 |
|----|----------|
| devices | 设备配置、在线信息及批次摘要的 evaluation_status/diagnosis_conclusion/health_score/coverage |
| sensor_data | 设备/批次/真实通道波形、采样率、是否已分析与时间 |
| diagnosis | 精确缓存身份、两维状态/nullable 分数/coverage、版本化 engine_result、转频与分析时间 |
| alarms | 统一诊断产生的设备/通道预警或故障告警、去重/处理信息 |
| collection_tasks | 采集任务生命周期，不与诊断状态混用 |

设备机械参数是配置，纯算法只接收已验证对象。原始波形不随重新诊断改写；历史 `order_analysis/full_analysis` 等物理列保留，不作为新诊断状态的兼容解释来源。

## 精确键、历史行与摘要

新缓存身份为 `(device_id,batch_index,channel,denoise_method)`，方法证据使用真实通道号，channel=0 专用于批次摘要。保存追加历史行，不以查询后覆盖已有行的方式争抢同键；不新增唯一约束，不删除旧历史。

读取严格匹配四个字段，按 analyzed_at 降序、同时间 id 降序取最新。没有通道/去噪组合就不存在，不回退其他去噪、其他通道、批次 JSON 或旧 full_analysis。旧 channel/denoise 为 NULL 的行不补为新合法缓存，不借用其他通道参数。

设备与批次列表的轻摘要只查 `channel=0,denoise_method=none`，按有效时间优先及 id tie-break 选最新；手工通道分析不能替代批次摘要。只有批次摘要保存允许更新 Device 的诊断字段，非 none 变体不更新设备诊断。摘要只取状态/分数/coverage/时间，不加载大 JSON。

独立 `/order` 与批次转频更新只定位准确 channel=0/none 行，修改 rot_freq；不创建伪健康记录，不修改状态/分数/证据/analyzed_at，也不命中通道缓存。

## 规范 JSON、旧缓存与直接重评

新 engine_result 保存 `contract_version=1` 的完整 Domain，必须通过状态/覆盖/Evidence 身份与局部状态不变量。入库边界严格转换 NumPy、数组和非有限值；研究限定或 production_eligible=false 结果拒绝进入生产存储。

读取旧版本、缺版本或不满足不变量的 JSON 时，返回规范的 not_evaluable/unknown/null、coverage=none 与 `stored_contract_requires_reanalysis`，不从旧 status 或旧分数恢复结论。不存在精确缓存与存在但旧缓存不可用是两种不同情形。

直接重评读取规范 Evidence，重新应用业务策略并追加同键历史行，不重新运行数值算法。旧缓存需要重新分析时 HTTP 409；重新分析才从原始采样运行对象 Pipeline。两者均不能借其他通道或去噪数据凑出健康结论。

## 旧库最小迁移

devices 与 diagnosis 新增 `evaluation_status`、`diagnosis_conclusion`、`coverage`，默认分别 not_evaluable、unknown、none；health_score 在模型中改为 nullable Float。旧 status 混用评估与结论，无法可信回填，物理列保留但 ORM 不再映射。

当首次添加任一两维状态列时，该表旧 health_score 清空为 NULL，MySQL 同步将 health_score 改为 FLOAT NULL。状态列已存在的后续启动不再重复清空新分数；只缺 coverage 时补列不触发两维迁移的分数清空。SQLite 依动态类型保存 nullable 值，不为新模型类型机械重建旧表。

其他缺失列和索引继续按现有增量建表/补列/checkfirst 规则处理。保留原采样、历史 JSON、旧状态列与记录，不为旧 NULL 通道或去噪列推造身份。迁移并不代表旧诊断已重新评估，首次部署后旧记录等待显式重新分析；真实生产数据库迁移未在文档轮次执行。

## 统一批次事务与通知

HTTP 重新分析与后台 worker 共用 `services/diagnosis_workflow.py::process_batch`。在 `ANALYSIS_SEM=1` 内按真实通道排序读取同批数据，检查采样率一致，在线程池计算，保存各通道与 channel=0 摘要、更新原始数据已分析标记、生成规范告警，然后一次 commit。

计算、写缓存、标记或告警任一阶段失败都 rollback，整批事务不留半完成记录。单个通道在分析中合法形成未知结果仍可作为规范局部状态保存，不等于事务执行失败。commit 成功后才推送 diagnosis_update/new_alarm；浏览器推送失败只记日志，不撤销成功事务或触发重复计算。

## 批次保留与资源

普通 sensor_data 按 1–16 循环覆盖，batch_index>=101 的特殊/永久批次不按普通循环清理。诊断历史不因缓存键规范化强行合并。全设备重新分析逐批串行，线程池仍 max_workers=2，遵守 [2G 运行时](architecture.md)。
