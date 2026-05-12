# 风机齿轮箱智能故障诊断系统 — 云端服务（Cloud）

本文档面向**云端后端服务**，说明其架构、模块、配置与运行方式。

---

## 1. 项目概述

云端是系统的核心中枢，承担以下职责：

- **数据接入**：接收边端上传的振动传感器数据（支持压缩/原图两种模式）
- **故障诊断**：定时对未分析数据进行 FFT + IMF 能量 + 阈值分析（可扩展神经网络模型）
- **设备管理**：维护多台风机齿轮箱的设备信息、健康度、运行时长
- **告警生成**：根据诊断结果自动生成设备级与通道级告警
- **实时推送**：通过 WebSocket 向前端推送诊断更新
- **前端 API**：为 Dashboard、监测、诊断、告警等页面提供 RESTful 接口

---

## 2. 技术栈

| 组件 | 说明 |
|------|------|
| Python 3.10+ | 运行环境 |
| FastAPI | Web 框架 / API 服务 |
| Uvicorn | ASGI 服务器 |
| SQLAlchemy 2.0 | ORM 数据库操作 |
| SQLite / MySQL | 数据存储（默认 SQLite，零配置） |
| NumPy / SciPy | 信号处理与频谱分析 |
| APScheduler | 定时任务（已替换为异步协程） |
| python-jose | JWT 认证 |
| python-dotenv | 环境变量管理 |
| msgpack | 压缩数据传输（与边端配合） |

---

## 3. 目录结构

```
cloud/
├── app/
│   ├── main.py              # FastAPI 入口，含后台分析任务与生命周期管理
│   ├── models.py            # SQLAlchemy 数据表模型
│   ├── schemas.py           # Pydantic 请求/响应校验模型
│   ├── database.py          # 数据库引擎与会话管理
│   ├── core/
│   │   ├── config.py        # 全局配置（数据库、认证、分析参数等）
│   │   └── websocket.py     # WebSocket 连接管理器
│   ├── api/                 # RESTful 路由（按功能模块拆分）
│   │   ├── auth.py          # 登录认证 / JWT Token
│   │   ├── ingest.py        # 边端数据接入（含解压与批次管理）
│   │   ├── dashboard.py     # 设备总览统计
│   │   ├── monitor.py       # 实时监测数据查询
│   │   ├── diagnosis.py     # 诊断结果查询
│   │   ├── alarms.py        # 告警列表与处理
│   │   ├── devices/         # 设备 CRUD 与管理
│   │   ├── data_view/       # 原始数据 / 频谱 / 特征查看
│   │   └── collect.py       # 采集任务下发（前端 → 边端）
│   └── services/
│       ├── analyzer.py      # 故障分析引擎主入口（NN + DiagnosisEngine + 回退）
│       ├── nn_predictor.py  # 神经网络预测器（ONNX 等格式）
│       ├── diagnosis/       # 诊断算法库
│       │   ├── engine.py    # DiagnosisEngine 主调度器
│       │   ├── features.py  # 特征提取（FFT / 包络 / 阶次）
│       │   ├── rule_based.py # 规则诊断（回退方案）
│       │   └── ...
│       └── alarms/          # 告警生成逻辑
│           ├── channel.py   # 通道级振动特征告警
│           ├── device.py    # 设备级综合告警
│           └── diagnosis.py # 诊断结果告警
├── models/                  # 神经网络模型文件存放目录（.gitignore 忽略）
│   └── README.md
├── requirements.txt         # Python 依赖
└── README.md                # 本文档
```

---

## 4. 环境搭建

### 4.1 安装依赖

```bash
cd cloud
pip install -r requirements.txt
```

### 4.2 数据库配置（可选）

默认使用 **SQLite**，无需安装任何数据库软件，数据保存在 `cloud/turbine.db`。

如需切换为 **MySQL**：

1. 安装并启动 MySQL，创建数据库：

   ```sql
   CREATE DATABASE turbine_db CHARACTER SET utf8mb4;
   ```

2. 在项目根目录创建 `.env` 文件：

   ```ini
   USE_SQLITE=false
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=turbine
   DB_PASSWORD=turbine1234
   DB_NAME=turbine_db
   ```

---

## 5. 核心配置

配置集中在 `app/core/config.py`，支持通过 `.env` 文件覆盖。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `USE_SQLITE` | `true` | 是否使用 SQLite |
| `DATABASE_URL` | `sqlite:///./turbine.db` | 数据库连接串 |
| `API_HOST` | `0.0.0.0` | 服务监听地址 |
| `API_PORT` | `8000` | 服务端口 |
| `ANALYZE_INTERVAL_SECONDS` | `30` | 后台分析轮询间隔（秒） |
| `SENSOR_SAMPLE_RATE` | `25600` | 振动采样率（Hz） |
| `SENSOR_WINDOW_SECONDS` | `10` | 单次采集时长（秒） |
| `NN_ENABLED` | `false` | 是否启用神经网络预测 |
| `NN_MODEL_PATH` | `./models/turbine_fault_model.onnx` | 模型文件路径 |
| `ADMIN_PASSWORD` | `admin123` | 网页登录密码 |
| `SECRET_KEY` | `change-me-in-production-please` | JWT 签名密钥 |
| `EDGE_API_KEY` | `turbine-edge-secret` | 边端接入 API Key |

> **生产环境注意**：务必将 `SECRET_KEY` 和 `EDGE_API_KEY` 修改为随机长字符串。

---

## 6. 数据模型

### 6.1 设备表（`devices`）

| 字段 | 说明 |
|------|------|
| `device_id` | 设备唯一编号，如 `WTG-001` |
| `name` | 设备名称 |
| `location` | 安装位置 |
| `channel_count` | 振动通道数（默认 3） |
| `channel_names` | 通道名称映射 JSON |
| `sample_rate` | 采样率 Hz |
| `health_score` | 健康度 0-100 |
| `status` | 状态：`normal` / `warning` / `fault` / `offline` |
| `runtime_hours` | 累计运行时长 |
| `gear_teeth` | 齿轮参数 JSON |
| `bearing_params` | 轴承参数 JSON |
| `compression_enabled` | 边端是否启用压缩 |
| `downsample_ratio` | 降采样压缩比 |

### 6.2 传感器数据表（`sensor_data`）

| 字段 | 说明 |
|------|------|
| `device_id` | 设备编号 |
| `batch_index` | 批次序号 |
| `channel` | 通道号 |
| `data` | 振动信号数组（JSON） |
| `is_analyzed` | 是否已完成诊断 |
| `is_special` | 是否手动触发采集（特殊数据） |

**存储策略**：

- **普通数据**（`is_special=0`）：每个设备最多保留 16 个批次（`1~16`），新数据循环覆盖最旧批次。
- **特殊数据**（`is_special=1`）：手动触发采集，批次号从 `101` 起自增，永不覆盖。

### 6.3 诊断结果表（`diagnosis`）

记录每次分析的健康度、故障概率、IMF 能量、阶次分析等。

### 6.4 告警表（`alarms`）

记录通道级与设备级告警，支持已处理/未处理状态。

### 6.5 采集任务表（`collection_tasks`）

前端下发采集任务 → 边端轮询获取 → 边端完成上传后标记为完成。

---

## 7. 核心模块详解

### 7.1 数据接入（`api/ingest.py`）

边端通过 `POST /api/ingest/` 上传数据，支持两种模式：

- **原图模式**：直接传入 `channels` JSON
- **压缩模式**：传入 `compressed_data`（Base64 编码的 zlib + msgpack），云端自动解压

数据入库后 `is_analyzed=0`，等待后台分析任务处理。

### 7.2 后台分析任务（`lifespan.py` 中的 `analysis_worker`）

启动后以 `ANALYZE_INTERVAL_SECONDS` 为周期循环：

1. 查询所有存在未分析数据的设备
2. 按 `batch_index` 读取该批次所有通道数据
3. 调用 `analyzer.py` 执行故障诊断
4. 写入 `diagnosis` 表，标记数据为已分析
5. 更新设备健康度与状态
6. 调用 `alarms/` 包生成告警
7. 通过 WebSocket 广播诊断结果

### 7.3 故障分析引擎（`services/analyzer.py`）

分析流程：

1. 优先调用 `nn_predictor.py`（如果 `NN_ENABLED=true` 且模型加载成功）
2. 神经网络不可用则回退到**简化规则算法**：
   - FFT 频谱分析
   - IMF 能量分布（频带能量近似）
   - 阶次分析（齿轮 / 轴承故障特征频率）
   - 阈值判断生成健康度与状态

> 注意：当前算法为教学级简化实现，真实工业场景可替换为 EMD/VMD、小波包分析、深度学习等高级方法。

### 7.4 认证体系（`api/auth.py`）

- **前端用户**：通过 `POST /api/auth/login` 密码登录获取 JWT Token，后续请求携带 `Authorization: Bearer <token>`
- **边端设备**：请求头携带 `X-Edge-Key`，与云端 `EDGE_API_KEY` 一致即通过
- `optional_auth` 依赖同时支持两种认证方式

### 7.5 WebSocket 实时推送（`core/websocket.py`）

前端连接 `ws://<host>/ws/monitor`，可实时接收：

- 诊断更新（`diagnosis_update`）
- 告警通知
- 心跳应答（`pong`）

---

## 8. 启动方式

### 开发模式（热重载）

```bash
cd cloud
python -m app.main
```

或

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 生产模式

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

启动成功后访问：

- API 文档（Swagger UI）：`http://localhost:8000/docs`
- 根接口：`http://localhost:8000/`

---

## 9. 数据流概览

```
┌─────────┐    HTTP POST /api/ingest     ┌─────────┐
│  边端    │ ───────────────────────────→ │  云端    │
│ (edge)  │   (压缩/原图 + X-Edge-Key)   │ (cloud) │
└─────────┘                              └────┬────┘
     ↑                                        │
     └──────── 轮询采集任务 ←─────────────────┤
                  /api/collect/poll           │
                                              ↓
                                    ┌─────────────────┐
                                    │  sensor_data    │
                                    │  (待分析数据)    │
                                    └─────────────────┘
                                              │
                                              ↓
                                    ┌─────────────────┐
                                    │ analysis_worker │
                                    │ (定时诊断分析)   │
                                    └─────────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ↓                         ↓                         ↓
            ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
            │  diagnosis  │          │   devices   │          │   alarms    │
            │  (诊断结果)  │          │ (更新健康度) │          │  (告警记录)  │
            └─────────────┘          └─────────────┘          └─────────────┘
                    │                         │                         │
                    └─────────────────────────┼─────────────────────────┘
                                              ↓
                                    ┌─────────────────┐
                                    │   WebSocket     │
                                    │  /ws/monitor    │
                                    └─────────────────┘
                                              │
                                              ↓
                                    ┌─────────────────┐
                                    │     前端页面     │
                                    │  (Dashboard/监测)│
                                    └─────────────────┘
```

---

## 10. 部署建议

1. **使用虚拟环境**：`python -m venv venv`，避免依赖冲突
2. **反向代理**：生产环境使用 Nginx 反向代理到 Uvicorn，处理 HTTPS 与静态资源
3. **数据库迁移**：SQLite 适合开发与小型部署；生产环境建议 MySQL + Alembic 正式迁移
4. **模型部署**：将训练好的 `.onnx` 模型放入 `models/` 目录，开启 `NN_ENABLED=true`
5. **安全配置**：
   - 修改 `SECRET_KEY`、`EDGE_API_KEY`、`ADMIN_PASSWORD`
   - 关闭 `allow_origins=["*"]`，限定前端域名
6. **日志与监控**：配置 Uvicorn/FastAPI 日志级别，接入 Prometheus/Grafana（可选）

---

## 11. 常见问题

**Q: 启动时报数据库表不存在？**  
A: `init_db()` 会在启动时自动建表。若修改了模型字段，可删除 `turbine.db` 重新启动（开发环境），或使用 `database.py` 中的自动迁移逻辑。

**Q: 边端上传失败 / 401 Unauthorized？**  
A: 检查边端 `EDGE_API_KEY` 与云端 `.env` 中配置是否一致。

**Q: 神经网络预测未生效？**  
A: 确认 `NN_ENABLED=true`，且模型文件路径正确。查看控制台日志中 `[NN]` 前缀的加载信息。

**Q: 如何添加新设备？**  
A: 调用 `POST /api/devices/` 接口，或在 `main.py` 的 `lifespan` 中预定义默认设备。
