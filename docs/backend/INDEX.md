# 后端文档索引

后端文档按稳定业务边界组织，不镜像 `cloud/app/` 文件树。函数签名以源码 docstring 为准，外部 HTTP/WebSocket 字段以 [API 文档](../api/backend_api.md) 为准。

| 文档 | 责任 |
|------|------|
| [架构与运行时](architecture.md) | 分层、依赖方向、线程池、串行分析、严格 JSON 与 2G 内存约束 |
| [业务服务](services.md) | 后台分析、诊断摘要、告警和离线监测的输入/副作用与组合关系 |
| [诊断编排](diagnosis.md) | Engine/ensemble、参数门控、转速工况、评分与缓存边界 |
| [证据、评估与诊断状态](assessment.md) | #77/#84 核心：类型化两维状态、对象覆盖、共同依赖融合、单源评分和直接重评；公开接入状态见文内说明 |
| [持久化](persistence.md) | 表、批次保留、诊断缓存、最新记录规则与增量迁移 |
| [DC24 云端服务](acquisition.md) | 原始 counts 显示分析、示波内存窗口、完整数组与显示摘要 |

## 相关边界

- 算法数学目的、单位、适用前提和验证状态：[算法模块索引](../algorithms/INDEX.md)
- REST/WS 请求响应与前后端影响：[后端 API](../api/backend_api.md)、[前后端交互](../api/frontend_backend_interaction.md)
- 测试分层、运行方式和数据依赖：[测试索引](../tests/INDEX.md)
- 文档组织决策：[ADR 0003](../adr/0003-module-contract-documentation.md)
