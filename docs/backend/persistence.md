# 持久化与诊断缓存契约

ORM 类型以 `cloud/app/models.py` 为准；外部字段见 [API](../api/backend_api.md)。诊断状态、Evidence 和重评语义见 [证据契约](assessment.md)，读写唯一入口为 `services/diagnosis_store.py`。

## 表与所有权

| 表 | 稳定内容 |
|----|----------|
| devices | 设备配置、在线信息及批次摘要的 evaluation_status/diagnosis_conclusion/health_score/coverage |
| sensor_data | 设备/批次/真实通道波形、显示采样率、仅旧 NULL 迁移使用的诊断采样率覆盖、是否已分析与时间 |
| diagnosis | 精确缓存身份、两维状态/nullable 分数/coverage、版本化 engine_result、转频与分析时间 |
| alarms | 统一诊断产生的设备/通道预警或故障告警、去重/处理信息 |
| collection_tasks | 采集任务生命周期，不与诊断状态混用 |
| acquisition_jobs | DC24 采集生命周期、显示分析选项、启用通道、完成元数据与已登记诊断批次身份 |

设备机械参数是配置，纯算法只接收已验证对象。原始波形不随重新诊断改写；历史 `order_analysis/full_analysis` 等物理列保留，不作为新诊断状态的兼容解释来源。

## 波形来源与统一读取

`sensor_data.data` 沿用现有 JSON 列表达两类来源，来源对象不需要新增波形列或改写云端数值数组；旧记录缺失的 `sample_rate` 由启动迁移单独处理：

- 云端既有记录继续保存数值数组，读取时仅在内存转换为 float64，原 JSON 数值不变。
- DC24 文件记录保存来源对象，包含 `kind=dc24_counts`、采集任务 `job_id`、原始 `counts.i32` 路径以及半开样本区段 `start_sample`/`end_sample`。文件是四路交错 little-endian int32；`SensorData.channel` 的 1~4 对应文件列 0~3。
- 文件只按区段和真实通道读入内存并转为 float64，不保存浮点波形副本，不做统一归一化或工程单位转换。

`services/waveform.py::load_waveform` 统一返回通道数组、显示采样率 `sample_rate`、诊断采样率 `diagnosis_sample_rate` 和 records。DataView 各数值/研究/导出接口与 Monitor 最新/历史接口使用 `sample_rate`；`diagnosis_workflow.process_batch` 使用 `diagnosis_sample_rate`。普通记录的 `diagnosis_sample_rate_override` 为 NULL，两者相等。仅旧 NULL 记录迁移后允许 override 非 NULL，此时诊断读取 override，显示读取仍用 sample_rate。诊断缓存键和最新记录查询规则不变，Monitor 历史列表继续复用已查询 records，保持常数 SQL 查询数。

读取层不查询 Device，也不套用运行时 fallback。显示或诊断候选值为 0/NULL 时抛出 `batch_sample_rate_missing`；0 是迁移写入的“不可诊断”标记，不是真实采样率。显示采样率不一致抛出 `batch_channel_sample_rates_must_match`，诊断采样率不一致抛出 `batch_channel_diagnosis_sample_rates_must_match`。

## DC24 完成登记事务

完整采集的 `counts.i32` 是诊断文件源。完成时按统一配置窗口和任务 `enabled_channels` 创建 `is_special=1`、`batch_index>=101` 的记录；每个窗口只保存来源对象和实际起止样本，短记录形成一个窗口，末段不补齐。设备以真实 `agent_id` 自动取得或创建，无需用户绑定。

`AcquisitionJob.result_metadata.diagnosis_device_id/diagnosis_batches` 是完成响应中的登记身份。远程 ZIP `/upload`、本地单次原件 `/upload?local_directory=...` 和流式 `finish-stream` 共用登记服务，在同一数据库事务中写入所有窗口、登记身份和任务终态；任一步失败不会留下“任务已完成但只登记部分窗口”的状态。终态重试直接返回原任务，两个完成入口由同一分析锁串行化，不能重复占用批次号。本地单次与流式任务均在 `result_metadata.local_directory` 保存现场原件绝对目录，诊断来源路径指向其中实际的 `counts.i32`；单次 record 缺少该文件时，后端在同一现场目录从已校验 CSV 生成它，系统不生成后端或浮点波形副本。移动或删除原件后，既有批次不能继续读取。登记后每批 `is_analyzed=0`，由现有 worker 按统一批次事务逐批完成，已完成的窗口即可查询，不等待同一记录的其他窗口。

DC24 文件批次的选段重诊复用 `next_special_batch_index` 与 `register_counts_window`，在同一原件上登记新的半开区间和真实通道集合，可重新启用原任务未选通道。新记录使用新的永久特殊批次号并进入统一批次事务；无选择参数的重诊仍直接处理原批次。数据库数组批次不接收文件选段参数。

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

其他缺失列和索引继续按现有增量建表/补列/checkfirst 规则处理。旧 `sensor_data` 缺少 `sample_rate` 或可空 `diagnosis_sample_rate_override` 列时先补列。origin/main 的 DataView/Monitor 对 NULL 使用 `SENSOR_SAMPLE_RATE`，diagnosis_workflow 则使用 `device.sample_rate`，因此不能用一个回填值同时保持两种历史行为。

启动迁移只处理 `sample_rate IS NULL` 的旧记录：override 写为同 `device_id` 的设备采样率；设备或设备采样率不存在时写 0，明确表示不可诊断。随后通过 SQL 参数把这些记录的 sample_rate 物化为统一配置 `SENSOR_SAMPLE_RATE`，保留旧显示/Monitor 语义。已有非 NULL sample_rate 和已有 override 不改写，新记录 override 永远为 NULL。该覆盖是历史迁移数据，不是运行时 fallback，0 不得作为真实采样率参与计算。

`acquisition_jobs.enabled_channels` 为新增 JSON 列；旧任务该列为 NULL，读取与完成登记沿用统一配置的全部有效通道，不改写历史任务。保留原采样、历史 JSON、旧状态列与记录，不为旧 NULL 通道或去噪列推造身份。迁移并不代表旧诊断已重新评估，首次部署后旧记录等待显式重新分析；真实生产数据库迁移未在文档轮次执行。

## 统一批次事务与通知

HTTP 重新分析与后台 worker 共用 `services/diagnosis_workflow.py::process_batch`。在 `ANALYSIS_SEM=1` 内经统一波形读取入口按真实通道排序取得同批数据，分别检查显示与诊断采样率一致，并以 `diagnosis_sample_rate` 在线程池计算，保存各通道与 channel=0 摘要、更新原始数据已分析标记、生成规范告警，然后一次 commit。

计算、写缓存、标记或告警任一阶段失败都 rollback，整批事务不留半完成记录。单个通道在分析中合法形成未知结果仍可作为规范局部状态保存，不等于事务执行失败。commit 成功后才推送 diagnosis_update/new_alarm；浏览器推送失败只记日志，不撤销成功事务或触发重复计算。

## 批次保留与资源

普通 sensor_data 按 1–16 循环覆盖，batch_index>=101 的特殊/永久批次不按普通循环清理。诊断历史不因缓存键规范化强行合并。全设备重新分析逐批串行，线程池仍 max_workers=2，遵守 [2G 运行时](architecture.md)。
