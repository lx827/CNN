# 文档索引

本页只负责入口导航。文档责任边界见 [ADR 0003](adr/0003-module-contract-documentation.md)，Agent 操作约束见 [AGENTS](../AGENTS.md)。

## 开始

| 目标 | 入口 |
|------|------|
| 项目概述与快速开始 | [README](../README.md) |
| 环境、命令、红线与代码导航 | [AGENTS](../AGENTS.md) |
| 计算库源码构建、依赖分组与 ISA 缓存 | [计算库构建说明](native_compute.md) |
| C++ 加速算法的模块、接口与内存规则 | [cpp-accelerate skill](../.claude/skills/cpp-accelerate/SKILL.md)、[ADR 0007](adr/0007-native-algorithm-module-interfaces.md) |
| 整体系统结构 | [系统架构](系统架构.md) |
| 域词汇 | [GLOSSARY](../GLOSSARY.md) |
| 云端、DC24、脚本说明 | [cloud README](../cloud/README.md)、[dc24 README](../dc24/README.md)、[scripts README](../scripts/README.md) |

## 契约文档

| 边界 | 权威入口 | 内容 |
|------|----------|------|
| 算法族 | [算法模块索引](algorithms/INDEX.md) | 数学目的、工况、单位、前提、Pipeline、不可判定、复杂度与验证状态 |
| 外部 API | [后端 API](api/backend_api.md) | REST/WS 请求响应、认证、错误与 OpenAPI |
| 前后端交互 | [交互映射](api/frontend_backend_interaction.md) | 前端调用点与后端端点的影响关系 |
| 后端业务 | [后端索引](backend/INDEX.md) | 架构运行时、业务服务、诊断编排、持久化和 DC24 云端服务 |
| 诊断证据与状态核心 | [证据、评估与诊断](backend/assessment.md) | #77/#84 的依赖融合、两维状态、覆盖和单源评分；公开接入状态在文内标注 |
| 前端 | [前端索引](frontend/INDEX.md) | 前端模块导航、API 封装与组件/服务说明 |
| 测试 | [测试索引](tests/INDEX.md) | 测试分层、运行方式、数据依赖和验证边界 |
| 架构决策 | [ADR 0001](adr/0001-uv-workspace-python-313.md)、[ADR 0002](adr/0002-edge-crossbuild-cloud-systemd.md)、[ADR 0003](adr/0003-module-contract-documentation.md)、[ADR 0004](adr/0004-evidence-and-diagnosis-state.md)、[ADR 0005](adr/0005-diagnosis-native-benchmark-gate.md)、[ADR 0006](adr/0006-native-diagnosis-compute-package.md) | uv workspace、部署、模块文档、诊断证据/状态与原生计算库决策 |
| Agent 工作流 | [Issue 跟踪](agents/issue-tracker.md)、[Triage 标签](agents/triage-labels.md)、[域文档](agents/domain.md) | Issue、标签、词汇与 ADR 约定 |

## 算法理论与数据

- [经典算法原理](算法原理.md)：公式推导、物理意义和参考文献。
- [诊断算法体系全景](诊断算法体系全景.md)：诊断业务组合、评分与集成背景。
- [小波与模态分解理论](algorithms/wavelet_and_modality_decomposition.md)：保留的理论资料。
- [复合研究流程](algorithms/composite/INDEX.md)：#75 核心阶段、四阶 MSB、相位前提、专用研究入口与生产隔离。
- [数据集说明](datasets.md)：路径、命名、采样率和机械参数。
- [行星齿轮箱诊断进展](行星齿轮箱诊断进展.md)：阶段性评估与限制。

## 采集、边端与运维

- [DC24 采集操作与实现](DC24_ACQUISITION.md)
- [从传感器到 CSV](DC24_SIGNAL_TO_CSV.md)
- [DC24 实测协议](DC24_PROTOCOL.md)
- [树莓派直连配置](树莓派直连配置.md)
- [Rust 边端 README](../edge/README.md) 与 [FFI 契约](../edge/FFI.md)
- [部署指南](部署指南.md)、[操作手册](操作手册.md)、[服务器命令速查](服务器命令速查.md)
- [边端交叉编译构建](../deploy/edge/README.md)
- [CQU 训练仓库与系统交付边界](CQU_TRAINING_HANDOFF.md)

## 现场资料与历史记录

这些资料保留其日期和验证语境，不作为当前函数签名来源。

- [现场数据交接 2026-10-20](FIELD_DATA_HANDOFF_20261020.md)
- [现场设备资料 2026-10-23](FIELD_EQUIPMENT_20261023.md)
- [DC24 工作交接 2026-11-07](DC24_HANDOFF_20261107.md)
- [DC24 采集工作记录](DC24_ACQUISITION_WORKLOG.md)
- [Rust 边端工作记录](RUST_EDGE_WORKLOG.md)
- [架构整顿记录 2026-10-21](架构整顿记录_20261021.md)
- [评估报告 2026-05-21](评估报告_20260521.md)
- [论文与专利评估 2026-10-17](论文与专利评估_20261017.md)
- [Bug 登记表](Bug登记表.md)
- [CQU × O9 工作日志（外部训练库）](https://github.com/lx827/wavelet_study/blob/o9-v1-kk/docs/CQU_O9_WORK_LOG.md)

## 文档检查

```bash
bash docs/internal/check_markdown_links.sh
```

检查相对链接、算法模块必需结构和已撤销镜像目录的引用。该命令只验证文档结构，不替代算法或 API 测试。
