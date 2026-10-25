# 文档索引

> **文档用途**：统一组织项目所有文档，方便 AI Agent 和人类用户快速定位。
> **维护要求**：新增文档时，必须在此索引中添加条目。

---

## 快速导航

### 📘 项目文档

| 文档 | 路径 | 用途 |
|------|------|------|
| [README](../README.md) | `README.md` | 项目概述、快速开始 |
| [AGENTS](../AGENTS.md) | `AGENTS.md` | AI Agent 环境配置、开发命令、关键代码路径 |
| [系统架构](./系统架构.md) | `docs/系统架构.md` | 整体架构、模块职责与目录结构 |
| [算法原理](./算法原理.md) | `docs/算法原理.md` | 轴承与齿轮诊断的经典理论、公式与参数 |
| [诊断算法体系全景](./诊断算法体系全景.md) | `docs/诊断算法体系全景.md` | 5 子系统串联：方法公式、投票逻辑、评分机制 |
| [快速启动说明](./快速启动说明.md) | `docs/快速启动说明.md` | 本机启动后端、前端与数据回放 |
| [部署指南](./部署指南.md) | `docs/部署指南.md` | 阿里云 ECS 部署步骤 |
| [操作手册](./操作手册.md) | `docs/操作手册.md` | 系统日常操作流程 |
| [服务器命令速查](./服务器命令速查.md) | `docs/服务器命令速查.md` | SSH、服务、日志等常用命令 |

---

### 📄 项目记录与评估

| 文档 | 路径 | 用途 |
|------|------|------|
| [Bug 登记表](./Bug登记表.md) | `docs/Bug登记表.md` | 已发现 Bug 的汇总与修复状态 |
| [2026-10-21 架构整顿](./架构整顿记录_20261021.md) | `docs/架构整顿记录_20261021.md` | 摘要读模型、响应性能根因、修复验证与剩余问题 |
| [2026-05-21 评估报告](./评估报告_20260521.md) | `docs/评估报告_20260521.md` | 算法与系统评估结果 |
| [2026-10-17 论文与专利评估](./论文与专利评估_20261017.md) | `docs/论文与专利评估_20261017.md` | 论文、专利材料与创新点评估 |
| [行星齿轮箱诊断进展](./行星齿轮箱诊断进展.md) | `docs/行星齿轮箱诊断进展.md` | 行星齿轮箱诊断的阶段性进展 |

### 📍 现场数据交接

| 文档 | 路径 | 用途 |
|------|------|------|
| [现场数据交接记录](./FIELD_DATA_HANDOFF_20261020.md) | `docs/FIELD_DATA_HANDOFF_20261020.md` | 设备、通道、CSV 清单、已知限制与待确认事项 |
| [现场设备资料汇总](./FIELD_EQUIPMENT_20261023.md) | `docs/FIELD_EQUIPMENT_20261023.md` | 机械参数、通道映射、手册与铭牌转录 |

---

### 🔧 后端文档

| 文档 | 路径 | 用途 |
|------|------|------|
| [后端目录索引](./backend/INDEX.md) | `docs/backend/INDEX.md` | **按文件模块结构组织后端代码** |
| [后端 API 接口](./api/backend_api.md) | `docs/api/backend_api.md` | REST API 和 WebSocket 端点完整文档 |
| [后端服务层接口](./backend/services.md) | `docs/backend/services.md` | 服务层所有公共函数/类接口文档 |
| [小波与模态分解算法](algorithms/wavelet_and_modality_decomposition.md) | `docs/algorithms/wavelet_and_modality_decomposition.md` | VMD、EMD、小波等信号分解方法 |

---

### 🎨 前端文档

| 文档 | 路径 | 用途 |
|------|------|------|
| [前端目录索引](./frontend/INDEX.md) | `docs/frontend/INDEX.md` | **按文件模块结构组织前端代码** |
| [前端 API 封装](./frontend/frontend_api.md) | `docs/frontend/frontend_api.md` | 前端 API 封装和 Vue 组件接口文档 |
| [前端服务层接口](./frontend/frontend_services.md) | `docs/frontend/frontend_services.md` | Stores、Utils、Components 接口文档 |

---

### 🔄 前后端交互文档

| 文档 | 路径 | 用途 |
|------|------|------|
| [前后端交互映射](./api/frontend_backend_interaction.md) | `docs/api/frontend_backend_interaction.md` | 前端组件与后端 API 的调用关系映射 |

---

### 🧪 测试与脚本文档

| 文档 | 路径 | 用途 |
|------|------|------|
| [测试套件索引](./tests/INDEX.md) | `docs/tests/INDEX.md` | 回归测试、方法评估、专项测试的完整索引 |
| [运维脚本索引](./scripts/INDEX.md) | `docs/scripts/INDEX.md` | 服务器运维调试脚本的完整索引 |

---

## 文档使用指南

### 何时查阅哪个文档？

| 场景 | 查阅文档 |
|------|----------|
| 了解项目整体架构 | `README.md`, `docs/系统架构.md` |
| 了解诊断算法数学公式与系统交互 | `docs/算法原理.md`, `docs/诊断算法体系全景.md` |
| 配置开发环境 | `AGENTS.md` |
| 修改后端 API 端点 | `docs/api/backend_api.md` → `docs/api/frontend_backend_interaction.md` |
| 修改后端服务函数 | `docs/backend/services.md` |
| 定位后端代码位置 | `docs/backend/INDEX.md` |
| 修改前端 API 调用 | `docs/frontend/frontend_api.md` → `docs/api/frontend_backend_interaction.md` |
| 修改前端组件/工具 | `docs/frontend/frontend_services.md` |
| 定位前端代码位置 | `docs/frontend/INDEX.md` |
| 部署到服务器 | `docs/部署指南.md`, `docs/操作手册.md` |
| 启动本机环境 | `docs/快速启动说明.md` |
| 查找服务器命令 | `docs/服务器命令速查.md` |
| 处理现场设备数据 | `docs/FIELD_DATA_HANDOFF_20261020.md`, `docs/FIELD_EQUIPMENT_20261023.md` |
| 运行/编写测试 | `docs/tests/INDEX.md` |
| 服务器运维调试 | `docs/scripts/INDEX.md` |

### 修改代码时的文档同步规则

| 代码变更类型 | 需要同步更新的文档 |
|-------------|-------------------|
| 新增/修改/删除 API 端点 | `backend_api.md` + `frontend_backend_interaction.md` |
| 新增/修改/删除服务层函数 | `services.md` |
| 新增/修改/删除前端 API 封装 | `frontend_api.md` + `frontend_backend_interaction.md` |
| 新增/修改/删除前端组件 | `frontend_services.md` |
| 新增/重命名/删除文件 | 对应目录的 `INDEX.md` |
| 修改函数签名（参数/返回值） | 对应接口文档 |
| 修改前后端数据格式 | 所有相关文档 |

---

## 文档结构总览

```
docs/
├── INDEX.md                          # 本文档（文档索引）
├── 系统架构.md                       # 整体架构与目录结构
├── 算法原理.md                       # 经典诊断算法理论
├── 诊断算法体系全景.md               # 5 子系统串联说明
├── 快速启动说明.md                   # 本机启动步骤
├── 部署指南.md                       # 服务器部署
├── 操作手册.md                       # 日常操作
├── 服务器命令速查.md                 # 运维常用命令
├── Bug登记表.md                      # 缺陷汇总与修复状态
├── 架构整顿记录_20261021.md          # 架构整顿记录
├── 评估报告_20260521.md              # 算法与系统评估
├── 论文与专利评估_20261017.md        # 论文与专利材料
├── 行星齿轮箱诊断进展.md             # 行星箱阶段性进展
├── FIELD_DATA_HANDOFF_20261020.md    # 现场数据交接
├── FIELD_EQUIPMENT_20261023.md       # 现场设备资料
│
├── api/                              # API 相关文档
├── backend/                          # 后端模块镜像文档（每个 .py 对应同名 .md）
├── frontend/                         # 前端文档
├── algorithms/                       # 专项算法文档
├── tests/                            # 测试文档
├── scripts/                          # 脚本索引
└── internal/                         # 文档检查工具
```

> 说明：`docs/backend/app/` 下的文档与 `cloud/app/` 源码一一对应，文件名保持英文，便于按模块定位。

---

*文档生成时间：2026-05-17*
*最近更新：2026-10-25*
*维护者：AI Agent（修改代码或文档结构时请务必同步更新）*
