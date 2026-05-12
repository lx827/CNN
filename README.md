# 风机齿轮箱智能故障诊断系统

> 边-云协同架构完整实现。默认零配置（SQLite），无需安装 Docker/MySQL 即可运行。
>
> **默认参数：** 8192 Hz 采样率，10 秒采集时长，支持数据压缩上传。支持真实 `.npy` 振动数据文件读取。

## 系统架构

```
边端采集（Python） → HTTP → 云端分析（FastAPI + SQLite/MySQL） ← HTTP/WebSocket ← Vue 前端
                              ↓
                         神经网络模型（预留接口）
```

| 模块 | 技术 | 路径 |
|------|------|------|
| 前端 | Vue 3 + Vite + Element Plus | `wind-turbine-diagnosis/` |
| 后端 | Python + FastAPI | `cloud/` |
| 数据库 | **SQLite**（默认）/ MySQL（可选） | `cloud/turbine.db` |
| 边端 | Python 采集客户端（支持模拟信号 / 真实 `.npy` 数据） | `edge/` |
| 神经网络 | ONNX / PyTorch / TensorFlow（预留接口） | `cloud/models/` |

## 环境要求

- Node.js >= 18
- Python >= 3.9

> 不需要 Docker，不需要安装 MySQL。默认使用 SQLite，数据保存在 `cloud/turbine.db` 文件中。

## 快速启动

### 方式一：一键启动（推荐）

双击 `start.bat`（Windows）或运行 `./start.sh`（Linux/Mac），会自动打开三个终端窗口分别启动云端、边端和前端。

### 方式二：手动启动（三个独立终端）

#### 终端 1：启动云端后端

```bash
cd cloud

# 创建虚拟环境（推荐，避免污染系统 Python）
python -m venv venv

# Windows 激活虚拟环境
venv/Scripts/activate

# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m app.main
```

第一次启动会自动创建 `cloud/turbine.db` 数据库文件和所有数据表。

服务启动后：

- API 地址：`http://localhost:8000`
- 自动文档：`http://localhost:8000/docs`（Swagger UI，可在线调试所有接口）

#### 终端 2：启动边端采集（可选）

> 不启动边端，系统也能正常运行（后端会自动用默认数据初始化）。启动边端后会有动态振动数据持续流入。

```bash
# 新开一个终端
cd edge

# 创建虚拟环境（推荐）
python -m venv venv
venv/Scripts/activate

# 安装依赖
pip install -r requirements.txt

# 启动采集器
python edge_client.py
```

边端会每 **10 秒**（可通过前端 Settings 页面动态调整，支持秒/分钟/小时）自动为所有配置的设备采集一批风机振动数据（**8192 Hz x 10 秒 = 81920 点/通道**，真实数据模式）上传到云端，同时每 **5 秒** 轮询所有设备是否有手动采集任务。

> 后端启动时会自动创建 **5 个模拟设备**（WTG-001 ~ WTG-005），健康度和状态各不相同。边端通过 `DEVICE_IDS` 配置可同时为多个设备上传数据。

#### 终端 3：启动前端界面

```bash
# 新开一个终端
cd wind-turbine-diagnosis

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

浏览器会自动打开 `http://localhost:3000`

#### 停止系统

在三个终端中分别按 **Ctrl + C**。

---

## 页面功能

| 页面 | 说明 |
|------|------|
| **Dashboard** | **所有设备**健康度卡片列表，点击卡片查看该设备的仪表盘、故障分布、部件状态 |
| **Monitor** | 手动触发采集（特殊数据）、实时振动波形（x 轴为**时间/秒**）、**后端真实 FFT 频谱**（x 轴为 Hz）、通道名称显示 |
| **Diagnosis** | 故障诊断结果、故障概率横向柱状图、RUL 寿命预测仪表盘 |
| **Alarm** | 告警统计卡片、告警记录分页列表（支持级别/设备过滤）、详情查看对话框（含通道信息、当前值、阈值对比、处理建议）、关联批次跳转、标记处理、删除单条告警 |
| **Settings** | 边端采集配置（上传间隔、轮询间隔、**采样率**、**采集时长**、**通道数**、**通道名称**、**数据压缩开关/压缩比**）+ **机械参数配置**（齿轮齿数、轴承几何参数，用于阶次跟踪自动标定故障特征频率）+ **通道级振动特征告警阈值配置**（RMS/峰值/峭度/峰值因子的预警/严重阈值，支持按设备独立设置）+ **批量应用到所有设备** |
| **新增** | 边端离线检测（5分钟无数据自动标记离线）、诊断结果关联批次（一键跳转原始数据）、WebSocket 实时推送（断线自动重连）、数据导出 CSV、批量删除批次、告警关联数据批次（可跳转查看原始数据）、设备独立告警阈值配置 |
| **DataView** | 表格展示设备及所有批次（**批次标签按诊断结果着色**：正常灰色/预警黄色/故障红色），点击批次默认加载时域波形；FFT、STFT、包络谱、**阶次谱（阶次跟踪）**、**倒谱分析（Cepstrum）**、**统计指标**（峰值/RMS/峭度/偏度/裕度/波形因子/脉冲因子/峰值因子等，加窗统计量输出时序图，窗口大小和滑动步长可调）需点击按钮后按需计算，防止过度消耗算力，支持删除单条或批量特殊数据；**诊断明细卡片**（频域/阶次/包络特征能量占比自动标红） |

---

## 项目结构

```
CNN/
├── architecture.md              # 系统架构设计文档
├── README.md                    # 本文件
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
│   ├── signal_generator.py      # 信号生成器（25600Hz, 4 种工况模拟 / 或读取 .npy 真实数据）
│   ├── compressor.py            # 压缩模块（降采样 + msgpack + zlib）
│   ├── requirements.txt
│   └── .env
│
└── wind-turbine-diagnosis/      # 前端
    ├── vite.config.js           # 代理配置
    └── src/
        ├── api/index.js         # 对接后端 API（数据格式转换兼容现有页面）
        ├── utils/request.js     # Axios 请求工具
        ├── views/               # 页面组件
        │   ├── Dashboard.vue    # 设备总览（所有设备健康度卡片）
        │   ├── Monitor.vue      # 实时监测（手动触发采集 + 波形图）
        │   ├── Diagnosis.vue    # 故障诊断结果
        │   ├── Alarm.vue        # 告警管理
        │   └── DataView.vue     # 数据查看（时域/FFT/STFT/包络谱/阶次谱/倒谱/统计指标）
        └── ...
```

---

## 数据流

```
1. 边端采集
   edge_client.py 每 10 秒生成振动信号（模拟：25600 Hz x 10 s = 256000 点；真实数据：8192 Hz x 10 s = 81920 点）
   → 【压缩】峰值保持降采样 + msgpack + zlib（压缩率 10~20 倍）
   → HTTP POST 到 /api/ingest/

2. 数据存储
   云端接收 → 自动识别压缩/原图模式 → 解压 → 写入 SQLite (sensor_data 表)
   - 普通数据：最多 16 批次循环覆盖（batch_index 1~16）
   - 特殊数据（手动触发）：batch_index 从 101 起自增，永不覆盖

3. 定时分析（后台线程每 30 秒）
   读取最近数据
   → 优先调用 nn_predictor.py（神经网络）
   → 如果 NN 未启用，回退到 analyzer.py（FFT + 阈值规则）
   → 生成健康度、故障概率、IMF 能量
   → 写入 diagnosis 表

4. 告警生成（两类告警）
   a) 通道级振动特征阈值告警：
      计算每通道的 RMS/峰值/峭度/峰值因子 → 与用户自定义阈值比较
      → 超阈值则写入 alarms 表（带通道号、通道名称）
   b) 设备级诊断结果告警：
      健康度 < 80 或某项故障概率 > 0.3
      → 写入 alarms 表（设备级）
   → WebSocket 推送给前端

5. 前端展示
   Dashboard / Monitor / Diagnosis / Alarm / DataView 页面
   → Dashboard：卡片展示**所有设备**健康度，点击切换查看详情
   → Monitor：选择设备后点击"请求采集"触发手动采集
   → DataView：表格展示，点击批次时间展开 FFT/STFT/包络谱/**阶次谱**/**倒谱分析**，支持删除
   → 时域图 x 轴：时间（秒）；频域图 x 轴：频率（Hz）
   → **所有频谱计算自适应实际采样率**（8192Hz / 25600Hz 等）
```

### 手动采集流程（特殊数据）

```
1. 前端点击"请求采集"
   → POST /api/collect/request?device_id=WTG-001
   → 云端创建 pending 任务，返回 task_id

2. 边端轮询（每 5 秒）
   → GET /api/collect/tasks?device_id=WTG-001
   → 发现 pending 任务，标记为 processing

3. 边端执行采集
   → 按云端配置的采样率采集数据
   → POST /api/ingest/（is_special=1, task_id=xxx）

4. 云端处理特殊数据
   → 分配 batch_index（101 起自增，永不覆盖）
   → 保存到 sensor_data 表
   → 后台分析服务自动分析
   → 标记任务为 completed

5. 前端轮询进度
   → GET /api/collect/tasks/{task_id}/status
   → 状态变化：pending → processing → completed
   → 完成后自动刷新 Monitor 页面显示最新数据
```

**特殊数据特点：**

- 不受 16 批次限制，永久保留
- batch_index 从 101 起自增
- 可在 DataView 中查看，带"特殊"标记
- 每个通道显示真实名称（如"轴承附近"、"驱动端"）
- **支持手动删除**（单条删除或批量清空）

**包络谱（轴承故障诊断）：**

- 使用希尔伯特变换提取信号包络
- 对包络信号做 FFT，检测轴承特征频率（BPFO/BPFI/BSF/FTF）
- 适用于轴承内圈/外圈/滚动体故障的早期发现

---

## 边端数据压缩

### 为什么需要压缩？

| 指标 | 数值 |
|------|------|
| 原始数据 | 3 通道 x 256000 点 x 8 字节 ≈ **2 MB** |
| 上传频率 | 每 10 秒一批 |
| 月流量（不压缩） | **~5 TB** |
| 月流量（压缩后） | **~250 GB** |

### 压缩流程

```
原始波形 256000点
    ↓ 峰值保持降采样（默认 8x，可配置）
32000点
    ↓ msgpack 序列化
二进制
    ↓ zlib 压缩
压缩包
    ↓ base64 编码
JSON字符串 ← HTTP 上传
```

### 配置方法

**推荐：通过前端 Settings 页面动态配置（无需重启边端）**

打开前端 **Settings** 页面：

- **数据压缩**开关：关闭后上传原始数据
- **压缩比**：1=不压缩，8=8倍压缩（81920→10240）
- 勾选 **"应用到所有设备"** → 一键同步所有 WTG 设备

边端每 30 秒自动从云端拉取最新配置，最长 30 秒生效。

**Fallback：编辑 `edge/.env`（需重启边端）**

```bash
# 多设备配置（一个边端实例同时为多个设备采集）
DEVICE_IDS=WTG-001,WTG-002,WTG-003,WTG-004,WTG-005

# 信号采集参数（真实数据模式下采样率由数据文件决定，不受此配置影响）
SAMPLE_RATE=25600        # 模拟模式采样率 Hz
DURATION=10             # 采集时长 秒（可被云端 window_seconds 覆盖）
DOWNSAMPLE_RATIO=8      # 降采样倍数（fallback，优先使用云端配置）

# 压缩开关（fallback，优先使用云端配置）
COMPRESSION_ENABLED=true
```

云端**自动兼容压缩/原图两种格式**。真实数据模式默认不压缩（ratio=1），模拟模式默认 8 倍压缩。

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
SAMPLE_RATE=8192
DURATION=10
DOWNSAMPLE_RATIO=8
COMPRESSION_ENABLED=true
USE_REAL_DATA=true                         # 是否使用真实 .npy 数据
DATA_DIR=D:\code\wavelet_study\dataset\CW\down8192_CW  # 真实数据目录
SIMULATE_OFFLINE_DEVICE=WTG-003            # 指定模拟离线的设备编号
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
- 支持 **批量应用到所有设备**（`PUT /api/devices/batch-config`）
- 本地 `.env` 中的值作为 fallback 兜底

---

## 神经网络接口（预留）

系统已为神经网络预测预留了完整接口，你可以无缝接入自己训练的模型。

### 预留位置

| 文件 | 作用 |
|------|------|
| `cloud/app/services/nn_predictor.py` | 模型加载 + 推理入口 |
| `cloud/app/services/analyzer.py` | 优先调用 NN，失败自动回退简化算法 |
| `cloud/models/` | 放置模型文件 |
| `cloud/.env` | `NN_ENABLED` / `NN_MODEL_PATH` |

### 接入步骤

1. **训练模型**
   - 输入：振动信号时域数组（256000 点，或降采样后的 32000 点）
   - 输出：故障类型概率向量（如 6 类）
   - 框架：PyTorch / TensorFlow / Keras 均可

2. **导出模型**

   ```python
   # PyTorch 示例
   torch.onnx.export(model, dummy_input, "turbine_fault_model.onnx")
   ```

3. **放置模型**

   ```bash
   cp turbine_fault_model.onnx cloud/models/
   ```

4. **修改配置**
   编辑 `cloud/.env`：

   ```
   NN_ENABLED=true
   NN_MODEL_PATH=./models/turbine_fault_model.onnx
   ```

5. **实现推理代码**
   打开 `cloud/app/services/nn_predictor.py`，在 `predict()` 和 `_load_model()` 中补充你的模型加载和推理逻辑。文件里已给出 ONNX / PyTorch / TensorFlow 三种示例框架，取消注释并修改即可。

6. **重启后端**

   ```bash
   python -m app.main
   ```

此时系统会优先使用神经网络预测结果；如果模型加载失败或推理异常，**自动回退到简化规则算法**，保证系统不会崩溃。

---

## 切换到 MySQL（可选）

SQLite 适合开发和单机演示。如果需要多机部署或数据量很大，可以切换到 MySQL：

### 1. 安装 MySQL

- Windows：下载 [MySQL Installer](https://dev.mysql.com/downloads/installer/) 安装
- 或安装 [XAMPP](https://www.apachefriends.org/)（自带 MySQL + 管理面板）

### 2. 创建数据库

```sql
CREATE DATABASE turbine_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'turbine'@'%' IDENTIFIED BY 'turbine1234';
GRANT ALL PRIVILEGES ON turbine_db.* TO 'turbine'@'%';
FLUSH PRIVILEGES;
```

### 3. 修改配置

编辑 `cloud/.env`：

```
USE_SQLITE=false
DB_HOST=localhost
DB_PORT=3306
DB_USER=turbine
DB_PASSWORD=turbine1234
DB_NAME=turbine_db
```

### 4. 安装 PyMySQL

```bash
cd cloud
pip install pymysql cryptography
```

### 5. 重启后端

数据库会自动创建所有表。

---

## 常见问题

**Q1: 后端启动报错 `ModuleNotFoundError`**

- 确认已在虚拟环境中：`venv/Scripts/activate`
- 确认已安装依赖：`pip install -r requirements.txt`

**Q2: 边端上传失败 `Connection refused`**

- 确认后端已启动（`python -m app.main`）
- 确认 `edge/.env` 中的 `CLOUD_INGEST_URL` 地址正确

**Q3: 前端页面空白或接口报错**

- 确认已执行 `npm install`
- 确认后端已启动，前端通过代理访问 `localhost:8000`
- 打开浏览器 F12 → Network，查看具体接口报错

**Q4: 如何清空数据重新开始？**

- SQLite：直接删除 `cloud/turbine.db` 文件，重启后端即可
- MySQL：`DROP DATABASE turbine_db; CREATE DATABASE turbine_db;`

**Q5: 神经网络模型加载失败？**

- 检查 `cloud/.env` 中 `NN_ENABLED=true` 且 `NN_MODEL_PATH` 路径正确
- 检查是否安装了对应的推理库（如 `onnxruntime`、`torch`、`tensorflow`）
- 查看后端控制台输出的 `[NN]` 日志

**Q6: 如何关闭数据压缩？**

- 打开前端 **Settings** 页面，把"数据压缩"开关关闭，压缩比设为 1
- 勾选"应用到所有设备"，点击保存
- 边端约 30 秒内同步，此后上传原始数据
- （Fallback）编辑 `edge/.env` 将 `COMPRESSION_ENABLED=false`，重启边端

**Q7: DataView 中如何删除数据？**

- 点击表格中某批次的"删除此批次"按钮，可删除单条（含关联诊断结果）
- 点击"删除特殊数据"可删除该设备所有特殊数据
- 点击顶部"清空所有特殊数据"一键清空

**Q8: 包络谱是什么？**

- 包络谱是轴承故障诊断的常用方法，通过希尔伯特变换提取振动信号包络
- 在 DataView 中选中批次后，点击"计算包络谱"按钮即可查看
- 适用于检测轴承内圈、外圈、滚动体等早期故障特征

**Q9: DataView 的 FFT/STFT/统计指标为什么不自动显示？**

- 这些计算需要消耗后端算力（尤其 STFT 涉及大规模矩阵运算）
- 系统采用**按需计算**设计：默认只加载时域波形，其他分析功能点击按钮后才触发
- 计算完成后可随时"收起"，保持界面整洁

**Q10: 统计指标的加窗参数是什么？**

- 加窗统计量（峭度/偏度/RMS/峰值/裕度/峰值因子/波形因子/脉冲因子）按窗口滑动计算，输出**时序图**而非单一数值
- 窗口大小范围：64~8192 点，默认 1024 点
- 滑动步长范围：1~4096 点，默认窗口大小的一半

**Q11: 阶次谱是什么？**

- 阶次谱（Order Tracking）是旋转机械振动分析的专用方法，将时域信号按转频倍数重采样到角域，再做 FFT
- X 轴不再是频率（Hz），而是**阶次**（转频的倍数），使得不同转速下的频谱可以直接对比
- 系统自动通过频谱峰值法估计转频，支持设置转频搜索范围（默认 10~100 Hz）和每转采样点数（默认 1024）
- 图表中自动标注 1×/2×/3× 转频位置，方便识别齿轮啮合频率、轴承故障阶次等特征

**Q12: 倒谱分析是什么？**

- 倒谱分析（Cepstrum）是检测频谱中周期性结构的经典方法，流程：FFT → 取对数 → IFFT
- 倒谱横轴为"倒频率"（单位 ms），峰值位置对应频谱中的谐波族周期（`频率 = 1000 / 倒频率`）
- 适用于：齿轮箱边频带分析、转频估计、轴承周期性冲击检测
- 系统自动检测显著峰值并标注对应的频率，最大倒频率可配置（默认 500 ms）

**Q13: 如何修改边端上传间隔？**

- 打开前端 **Settings（边端配置）** 页面
- 选择设备，输入数字并选择单位（秒/分钟/小时）调整"自动采集间隔"
- 点击保存，约 30 秒内同步到边端
- 也可编辑 `edge/.env` 中的 `UPLOAD_INTERVAL` 后重启边端

**Q14: 配置修改后多久生效？**

- 边端每 30 秒自动从云端拉取最新配置
- 保存后最长等待 30 秒即可生效
- 重启边端可立即生效

**Q15: numpy 安装失败（Python 3.13）**

- `numpy==1.26.4` 不支持 Python 3.13
- 修改 `requirements.txt` 为 `numpy>=1.26.4` 后重新安装

**Q16: 健康度不变？**

- 确认边端已启动并正在上传数据
- 后端需要动态数据才会更新诊断结果；仅初始化数据不会持续变化
- 启动 `python edge_client.py` 产生动态数据后，等待 30 秒左右观察

**Q17: WTG-001 健康设备为什么也报故障？**

- 检查 Settings 页面中 WTG-001 的告警阈值是否过高
- 真实数据模式下，健康数据（H 组）的峰值约 0.045，峭度约 3.0；阈值应高于这些值
- 默认阈值已针对真实数据校准：Peak 0.06/0.15，Kurtosis 4.0/7.0，RMS 0.008/0.030

**Q18: 如何使用模拟信号而不是真实数据？**

- 编辑 `edge/.env`，将 `USE_REAL_DATA=false`
- 重启边端，此时使用 `signal_generator.py` 生成模拟振动信号（4 种工况）

**Q19: 离线设备为什么还显示旧的健康度？**

- 离线设备（超过 5 分钟无数据）Dashboard 会显示 "离线，暂无数据"，健康度为 null
- 这是正常行为，设备恢复上线后会自动更新

**Q20: 告警中的"关联数据批次"是什么？**

- 通道级告警会关联到产生该告警的数据批次（batch_index）
- 在 Alarm 页面点击"查看数据"可直接跳转到 DataView 查看该批次的原始波形和分析结果

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

---

## 扩展路线图

| 阶段 | 内容 |
|------|------|
| **当前** | 简化规则算法 + 5 设备模拟数据，系统完整可运行；支持云端控制压缩参数、批量设备配置、齿轮/轴承参数化诊断、阶次/包络/频谱融合特征 |
| **下一步** | 训练 CNN / 1D-CNN / LSTM 模型，接入 `nn_predictor.py` |
| **再下一步** | 边端接入真实传感器（串口 / NI DAQ / Modbus） |
| **后期** | 引入 InfluxDB 存储高频时序数据；多台风机接入；用户权限系统 |
