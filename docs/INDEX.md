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
| [架构设计](../architecture.md) | `architecture.md` | 系统架构设计 |
| [算法说明](../ALGORITHMS.md) | `ALGORITHMS.md` | 诊断算法说明 |
| [部署指南](../DEPLOY.md) | `DEPLOY.md` | 服务器部署指南 |
| [运维手册](../OPERATION.md) | `OPERATION.md` | 运维操作手册 |

---

### 🔧 后端文档

| 文档 | 路径 | 用途 |
|------|------|------|
| [后端目录索引](./backend/INDEX.md) | `docs/backend/INDEX.md` | **按文件模块结构组织后端代码** |
| [后端 API 接口](./api/backend_api.md) | `docs/api/backend_api.md` | REST API 和 WebSocket 端点完整文档 |
| [后端服务层接口](./backend/services.md) | `docs/backend/services.md` | 服务层所有公共函数/类接口文档 |

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

## 文档使用指南

### 何时查阅哪个文档？

| 场景 | 查阅文档 |
|------|----------|
| 了解项目整体架构 | `README.md`, `architecture.md` |
| 配置开发环境 | `AGENTS.md` |
| 修改后端 API 端点 | `docs/api/backend_api.md` → `docs/api/frontend_backend_interaction.md` |
| 修改后端服务函数 | `docs/backend/services.md` |
| 定位后端代码位置 | `docs/backend/INDEX.md` |
| 修改前端 API 调用 | `docs/frontend/frontend_api.md` → `docs/api/frontend_backend_interaction.md` |
| 修改前端组件/工具 | `docs/frontend/frontend_services.md` |
| 定位前端代码位置 | `docs/frontend/INDEX.md` |
| 部署到服务器 | `DEPLOY.md`, `OPERATION.md` |

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
│
├── api/                              # API 相关文档
│   ├── backend_api.md                # 后端 REST API + WebSocket 文档
│   └── frontend_backend_interaction.md # 前后端交互映射
│
├── backend/                          # 后端文档
│   ├── INDEX.md                      # 后端目录索引
│   └── services.md                   # 后端服务层接口文档
│
└── frontend/                         # 前端文档
    ├── INDEX.md                      # 前端目录索引
    ├── frontend_api.md               # 前端 API 封装文档
    └── frontend_services.md          # 前端服务层接口文档（Stores/Utils/Components）
```

---

*文档生成时间：2026-05-17*
*维护者：AI Agent（修改代码或文档结构时请务必同步更新）*
