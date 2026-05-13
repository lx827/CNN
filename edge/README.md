# Edge Client — 边端采集客户端

> 本文档说明 `edge/` 目录下的边端采集程序，负责模拟风机现场的工业网关，采集振动信号并上传至云端。

---

## 1. 模块概述

边端客户端模拟安装在风机现场的工业网关，核心职责：

1. **信号采集**：生成模拟振动信号或读取本地真实 `.npy` 数据文件
2. **数据压缩**：使用降采样 + msgpack + zlib 压缩，减少上传带宽
3. **数据上传**：通过 HTTP POST 将数据上传到云端 `/api/ingest/`
4. **任务轮询**：定期从云端获取手动采集任务，执行后上传结果
5. **动态配置**：支持云端动态调整上传间隔等参数

---

## 2. 文件结构

```
edge/
├── edge_client.py       # 主程序（采集 + 上传 + 任务轮询）
├── signal_generator.py  # 信号生成器（模拟/真实 .npy 数据）
├── compressor.py        # 数据压缩（降采样 + msgpack + zlib）
├── requirements.txt     # Python 依赖
├── .env                 # 边端配置文件
└── venv/                # Python 虚拟环境
```

---

## 3. 环境配置（`.env`）

```env
# 云端地址
CLOUD_INGEST_URL=http://localhost:8000/api/ingest/

# 设备列表（支持多设备，逗号分隔）
DEVICE_IDS=WTG-001,WTG-002,WTG-003,WTG-004,WTG-005

# 数据模式
USE_REAL_DATA=true
DATA_DIR=D:\code\wavelet_study\dataset\HUSTbear\down8192

# 信号参数
SAMPLE_RATE=8192
DURATION=10

# 压缩参数
COMPRESSION_ENABLED=true
DOWNSAMPLE_RATIO=8

# 轮询间隔
UPLOAD_INTERVAL=10
TASK_POLL_INTERVAL=5
```

### 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CLOUD_INGEST_URL` | `http://localhost:8000/api/ingest/` | 云端数据接入地址 |
| `DEVICE_IDS` | `WTG-001` | 设备编号列表，逗号分隔 |
| `USE_REAL_DATA` | `true` | `true`=读取 `.npy` 文件，`false`=生成模拟信号 |
| `DATA_DIR` | — | 真实数据目录（`.npy` 文件路径） |
| `SAMPLE_RATE` | `25600` | 采样率 Hz |
| `DURATION` | `10` | 单次采集时长（秒） |
| `COMPRESSION_ENABLED` | `true` | 是否启用数据压缩 |
| `DOWNSAMPLE_RATIO` | `8` | 降采样压缩比 |
| `UPLOAD_INTERVAL` | `10` | 自动上传间隔（秒） |
| `TASK_POLL_INTERVAL` | `5` | 任务轮询间隔（秒） |

---

## 4. 数据格式

### 4.1 真实数据模式（`.npy` 文件）

使用 HUSTbear 轴承数据集：

- **路径**：`DATA_DIR` 目录下的 `.npy` 文件
- **采样率**：8192 Hz（与 `SAMPLE_RATE` 配置一致）
- **文件命名**：`{负载}_{故障类型}_{转速模式}-{通道}.npy`
  - 负载：`0.5X` / `1X` / `1.5X` / `2X`
  - 故障类型：`N`（健康）/ `B`（球故障）/ `IR`（内圈）/ `OR`（外圈）/ `C`（复合）
  - 转速模式：`CS`（恒定转速）/ `VS`（变速）
  - 通道：`X` / `Y` / `Z`
- **示例**：`0.5X_B_VS_0_40_0Hz-X.npy`

### 4.2 模拟数据模式

当 `USE_REAL_DATA=false` 时，生成模拟振动信号：

- 正弦波 + 白噪声 + 周期性冲击（模拟轴承故障）
- 可调节故障类型、严重程度、转速等参数

---

## 5. 数据压缩流程

```
原始信号 (float64 数组)
    │
    ▼ 降采样
降采样信号 (长度 / DOWNSAMPLE_RATIO)
    │
    ▼ msgpack 序列化
二进制数据
    │
    ▼ zlib 压缩
压缩数据 (Base64 编码)
    │
    ▼ HTTP POST 上传
云端
```

压缩率通常可达 **10:1 ~ 50:1**，显著减少上传带宽。

---

## 6. 启动方式

```bash
cd /d/code/CNN/edge
. venv/Scripts/activate
pip install -r requirements.txt
python edge_client.py
```

一个边端实例可同时为多个设备（`WTG-001` ~ `WTG-005`）采集和上传数据，每个设备独立轮询、独立上传。

---

## 7. 运行流程

```
启动
  │
  ├──→ 拉取云端配置（上传间隔等）
  │
  ├──→ 为每个设备创建独立线程
  │      │
  │      ├──→ 采集信号（真实 .npy 或模拟生成）
  │      │
  │      ├──→ 压缩数据
  │      │
  │      ├──→ HTTP POST 上传至 /api/ingest/
  │      │
  │      └──→ 等待 UPLOAD_INTERVAL 秒，循环
  │
  └──→ 任务轮询线程
         │
         ├──→ GET /api/collect/tasks
         │
         ├──→ 若有 pending 任务，执行采集上传
         │
         └──→ 等待 TASK_POLL_INTERVAL 秒，循环
```

---

## 8. 多设备支持

边端客户端支持**一个实例管理多个设备**：

```env
DEVICE_IDS=WTG-001,WTG-002,WTG-003
```

每个设备：
- 独立的数据目录（按设备 ID 子目录查找 `.npy` 文件）
- 独立的上传线程
- 独立的批次索引

---

## 9. 常见问题

| 问题 | 解决 |
|------|------|
| 上传失败 / 连接超时 | 检查 `CLOUD_INGEST_URL` 是否正确，云端是否已启动 |
| `ModuleNotFoundError` | 确认已激活 venv，`pip install -r requirements.txt` |
| 找不到 `.npy` 文件 | 检查 `DATA_DIR` 路径是否正确，文件名格式是否匹配 |
| 数据上传成功但云端未显示 | 检查边端 `X-Edge-Key` 是否与云端 `EDGE_API_KEY` 一致 |
| 压缩后数据异常 | 检查 `SAMPLE_RATE` 和 `DOWNSAMPLE_RATIO` 配置是否合理 |
