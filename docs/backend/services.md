# 后端业务服务契约

本页记录跨请求稳定的服务职责和副作用，不复制函数签名。算法语义见 [算法模块索引](../algorithms/INDEX.md)，采集专用服务见 [DC24 云端服务](acquisition.md)。

## 多通道后台分析

`services/analyzer.py` 按真实通道排序，为每条记录建立 DiagnosisKey、选择本通道机械参数并运行 runtime 对象诊断；局部 Evidence 保留，批次按 `chN/object` 区分对象，再由 assessment 形成整体 Domain。没有旧通道共识或规则备用成功链。

- 不自行决定 HTTP 响应格式，不绕过 worker 的事务与严格 JSON 边界。
- 通道结果与批次结果保持明确层级；通道缺失或算法不可判定不能合成为伪健康设备。
- 多通道共识是辅助证据，不会把多数通道的未知变成确定正常。
- 去噪/计算失败通道保留局部 unknown/null、评估状态和原因，合法通道不被清空；总体 coverage 可为 partial。runtime 实际运行指定去噪，不把 none 冒充配置方法。

## 诊断摘要读模型

`services/diagnosis_queries.py` 统一 Dashboard 和批次列表的最新摘要规则：

- 设备摘要每设备一条，批次摘要每设备批次一条。
- 按 `analyzed_at`、`id` 降序选择；有效时间晚于空时间，同时间以较大 id 打破并列。
- 只选 channel=0、denoise=none 的批次摘要；手工通道分析不再覆盖设备/批次摘要。
- 只读取摘要列，不加载 `order_analysis`、`engine_result`、`full_analysis` 等大 JSON。
- 使用调用方 Session，不提交或关闭会话；空设备集合返回空结果。

## 告警服务

`services/alarms/__init__.py` 只消费校验通过的完整 Domain，不另读原始指标/健康阈值重判诊断。在线设备的有效 warning 生成 warning，fault 生成 critical；设备摘要和每个通道分别处理，沿用一小时同设备/通道、类别、级别、未处理去重。

normal、unknown、未评估、离线和研究限定结果均不生成机械诊断告警。告警建议直接来自 assessment，描述保留覆盖范围；旧逐指标 channel/device/diagnosis 告警实现已删除。设备阈值配置仍是配置接口，不等同于第二套诊断解释。

## 唯一事务编排

`diagnosis_workflow.process_batch` 被手工重新分析和后台 worker 共同调用，计算/通道与批次缓存/原始标记/告警同事务，commit 后再推 WS。故障 rollback 与缓存历史身份详见 [持久化](persistence.md)。只读谱和研究计算不借该事务写生产结果。

## 离线监测

离线监测只改变设备在线状态与相关推送，不删除历史健康度或诊断结果。设备离线不是机械健康证据，历史摘要仍按最新记录规则返回。

## 神经网络预留

`nn_predictor.py` 是预留推理边界。未加载真实模型时不得在文档或 API 中宣称具有训练后诊断能力；训练仓库与交付边界见 [CQU 训练交接](../CQU_TRAINING_HANDOFF.md)。
