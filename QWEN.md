# 风机齿轮箱智能故障诊断系统 — Qwen Context

## 项目概述

这是一个**边-云协同架构**的风机齿轮箱智能故障诊断系统，支持数据采集、存储、分析、诊断和可视化。系统默认零配置（SQLite），无需安装 Docker/MySQL 即可运行。

### 核心架构

```
边端采集（Python） → HTTP → 云端分析（FastAPI + SQLite/MySQL） ← HTTP/WebSocket ← Vue 前端
                              ↓
                         神经网络模型（预留接口）
```

| 模块 | 技术栈 | 路径 |
|------|--------|------|
| 前端 | Vue 3 + Vite + Element Plus | `wind-turbine-diagnosis/` |
| 后端 | Python + FastAPI | `cloud/` |
| 数据库 | SQLite（默认）/ MySQL（可选） | `cloud/turbine.db` |
| 边端 | Python 模拟采集器 | `edge/` |
| 神经网络 | ONNX / PyTorch / TensorFlow（预留） | `cloud/models/` |

### 环境要求

- Node.js >= 18
- Python >= 3.9
- 不需要 Docker，不需要 MySQL

---

## 项目结构

```
CNN/
├── QWEN.md                      # 本文件（项目上下文）
├── architecture.md              # 系统架构设计文档（详细）
├── README.md                    # 运行指南
├── OPERATION.md                 # 操作手册（纯步骤）
├── start.bat / start.sh         # 一键启动脚本
│
├── cloud/                       # 云端后端
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + 后台分析任务 + WebSocket
│   │   ├── database.py          # 数据库连接（SQLite / MySQL 自动切换）
│   │   ├── models.py            # 数据表模型（SQLAlchemy）
│   │   ├── schemas.py           # 数据校验模型（Pydantic）
│   │   ├── core/
│   │   │   ├── config.py        # 配置文件（数据库、端口、NN 开关、采样率）
│   │   │   └── websocket.py     # WebSocket 连接管理器
│   │   ├── api/                 # RESTful 接口
│   │   │   ├── ingest.py        # 边端数据接入（支持自动解压）
│   │   │   ├── dashboard.py     # 设备总览（含离线检测）
│   │   │   ├── monitor.py       # 实时监测（含后端 FFT 计算）
│   │   │   ├── diagnosis.py     # 诊断结果
│   │   │   ├── alarms.py        # 告警管理
│   │   │   ├── devices.py       # 设备列表
│   │   │   ├── data_view.py     # 数据查看（时域/FFT/STFT 实时计算）
│   │   │   └── collect.py       # 采集任务（手动触发）
│   │   └── services/
│   │       ├── analyzer.py      # 分析引擎：优先调用 NN，失败则回退简化算法
│   │       ├── alarm_service.py # 告警生成：通道级振动特征阈值 + 设备级诊断结果
│   │       └── nn_predictor.py  # 【神经网络预留接口】
│   ├── models/                  # 放置训练好的模型文件（.onnx / .pt / .pb）
│   ├── turbine.db               # SQLite 数据库文件（自动生成）
│   ├── requirements.txt
│   └── .env
│
├── edge/                        # 边端采集
│   ├── edge_client.py           # 主程序：生成信号 + 压缩 + 上传云端
│   ├── signal_generator.py      # 信号生成器（25600Hz, 4 种工况模拟）
│   ├── compressor.py            # 压缩模块（降采样 + msgpack + zlib）
│   ├── requirements.txt
│   └── .env
│
└── wind-turbine-diagnosis/      # 前端
    ├── vite.config.js           # 代理配置
    └── src/
        ├── api/index.js         # 对接后端 API
        ├── utils/request.js     # Axios 请求工具
        └── views/               # 页面组件
            ├── Dashboard.vue    # 设备总览（所有设备健康度卡片）
            ├── Monitor.vue      # 实时监测（手动触发采集 + 波形图）
            ├── Diagnosis.vue    # 故障诊断结果
            ├── Alarm.vue        # 告警管理
            └── DataView.vue     # 数据查看（时域/FFT/STFT/包络谱/阶次谱/倒谱/统计指标）
```

---

## 启动命令

### 方式一：一键启动

双击 `start.bat`（Windows）或运行 `./start.sh`（Linux/Mac），会自动打开三个终端窗口分别启动云端、边端和前端。

### 方式二：手动启动（三个独立终端）

#### 终端 1：云端后端

```bash
cd cloud
venv\Scripts\activate        # Windows 激活虚拟环境
# source venv/bin/activate   # macOS/Linux
python -m app.main
```

启动成功后访问：
- API: http://localhost:8000
- Swagger 文档: http://localhost:8000/docs

#### 终端 2：边端采集（可选，不启动系统也能运行）

```bash
cd edge
venv\Scripts\activate
python edge_client.py
```

边端每 **10 秒** 上传一批数据，每 **5 秒** 轮询采集任务。

#### 终端 3：前端界面

```bash
cd wind-turbine-diagnosis
npm install       # 首次需要
npm run dev
```

浏览器自动打开 http://localhost:3000

### 停止系统

在三个终端中分别按 **Ctrl + C**。

---

## 数据流

### 1. 边端 → 云端

```
edge_client.py 每 10 秒生成振动信号（25600 Hz × 10s = 256000 点/通道）
  → 峰值保持降采样 8x → 32000 点
  → msgpack + zlib 压缩（压缩率 10~20 倍，~100 KB/批）
  → HTTP POST 到 /api/ingest/
```

### 2. 云端接收 → 存储

```
云端接收 → 自动识别压缩/原图 → 解压 → 写入 sensor_data 表
  - 普通数据：最多 16 批次循环覆盖（batch_index 1~16）
  - 特殊数据（手动触发）：batch_index 从 101 起自增，永不覆盖
```

### 3. 后台分析（每 30 秒）

```
读取未分析数据 → 优先调用 NN → 失败回退简化规则算法
  → 生成健康度/故障概率/IMF 能量
  → 计算通道级振动特征（RMS/峰值/峭度/峰值因子）
  → 超阈值生成告警 → 写入 alarms 表
  → WebSocket 推送给前端
```

### 4. 前端展示

| 页面 | 功能 |
|------|------|
| **Dashboard** | 所有设备健康度卡片，点击查看详细仪表盘/故障分布/部件状态 |
| **Monitor** | 手动触发采集、实时振动波形（x 轴：时间/秒）、后端 FFT 频谱（x 轴：Hz） |
| **Diagnosis** | 故障诊断结果、故障概率柱状图、RUL 寿命预测、IMF 能量分布 |
| **Alarm** | 告警统计、分页列表、级别过滤、详情查看、标记处理 |
| **DataView** | 设备及批次表格、时域波形、FFT/STFT/包络谱/阶次谱/倒谱/统计指标（按需计算）、删除数据 |
| **Settings** | 边端采集配置、通道级振动特征告警阈值配置 |

---

## 关键配置

### 云端（`cloud/.env`）

```env
USE_SQLITE=true              # true=SQLite(默认), false=MySQL
DB_HOST=localhost            # MySQL 配置
DB_PORT=3306
DB_USER=turbine
DB_PASSWORD=turbine1234
DB_NAME=turbine_db
API_PORT=8000
NN_ENABLED=false             # 神经网络开关
NN_MODEL_PATH=./models/turbine_fault_model.onnx
```

### 边端（`edge/.env`）

```env
CLOUD_INGEST_URL=http://localhost:8000/api/ingest/
DEVICE_IDS=WTG-001,WTG-002,WTG-003,WTG-004,WTG-005
SAMPLE_RATE=25600
DURATION=10
DOWNSAMPLE_RATIO=8
COMPRESSION_ENABLED=true
```

---

## 重要特性

### 边端离线检测

- **机制**：比较设备 `last_seen_at` 与当前时间，超过 **5 分钟** 无数据标记为离线
- **实现位置**：`cloud/app/api/dashboard.py`
- **展示**：Dashboard 返回 `is_offline` 标志和 `effective_status`（离线时强制为 "offline"）
- **局限**：被动检测（仅查询时计算），无主动告警，固定阈值不可配置

### 数据压缩

- **流程**：峰值保持降采样 → msgpack 序列化 → zlib 压缩 → base64 编码
- **效果**：2 MB → ~100 KB/批，月流量从 ~5 TB 降至 ~250 GB
- **云端自动兼容** 压缩/原图两种格式

### 神经网络预留接口

- **位置**：`cloud/app/services/nn_predictor.py`
- **支持框架**：ONNX / PyTorch / TensorFlow
- **回退机制**：NN 加载失败自动回退到简化规则算法，系统不崩溃
- **接入步骤**：训练模型 → 导出到 `cloud/models/` → 修改 `.env` 启用 → 实现推理代码 → 重启后端

### 动态配置机制

- 边端启动时从云端拉取配置（`GET /api/devices/edge/config`）
- 运行中每 **30 秒** 刷新一次
- 前端 Settings 页面修改后最长 30 秒内同步到边端
- 本地 `.env` 中的值作为 fallback 兜底

---

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError` | 没在虚拟环境/依赖没装 | `venv\Scripts\activate` + `pip install -r requirements.txt` |
| 边端 `Connection refused` | 后端没启动 | 先启动 `python -m app.main` |
| 前端空白/报错 | 后端没启动/依赖没装 | 确认后端运行中；前端执行 `npm install` |
| 健康度不变 | 边端没启动 | 启动 `python edge_client.py` 产生动态数据 |
| 模型加载失败 | 路径错/缺推理库 | 检查 `NN_MODEL_PATH`；安装 `onnxruntime`/`torch` |
| 清空数据 | — | 删除 `cloud/turbine.db` 后重启后端 |
| numpy 安装失败（Python 3.13） | numpy==1.26.4 不支持 3.13 | 修改 `requirements.txt` 为 `numpy>=1.26.4` |

---

## 开发约定

### Python 虚拟环境

- 每个模块（cloud/edge）独立虚拟环境，避免依赖冲突
- 虚拟环境目录名统一为 `venv`
- 激活后再执行任何 Python 命令

### 前端

- Vite 开发服务器自动代理后端请求到 `localhost:8000`
- 使用 Axios 进行 HTTP 请求，工具函数在 `src/utils/request.js`
- API 封装在 `src/api/index.js`

### 数据表

| 表名 | 用途 |
|------|------|
| `devices` | 设备信息（健康度、状态、配置参数） |
| `sensor_data` | 传感器原始数据（普通/特殊批次） |
| `collection_tasks` | 采集任务（手动触发） |
| `diagnosis` | 诊断结果（关联批次） |
| `alarms` | 告警记录（通道级 + 设备级） |
