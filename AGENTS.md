# AGENTS.md — 风机齿轮箱智能故障诊断系统

> 本文档面向 AI Agent，包含环境配置、开发命令、部署流程和关键代码路径。人类用户请阅读 `README.md`。

---

## 1. 环境信息

| 环境 | OS | Python | Node.js | 说明 |
|------|-----|--------|---------|------|
| **本地开发** | Windows | 3.13.7 | ≥ 18 | 主要开发/调试环境 |
| **生产服务器** | Ubuntu 22.04 | 3.10 | — | 阿里云 ECS，2核2G |

**服务器关键信息：**

- 公网 IP：`8.137.96.104`
- systemd 服务名：`CNN.service`
- 部署路径：`/opt/CNN`
- **内存限制：2GB** — 多线程必须严格控制（见第7节）

---

## 2. 项目结构

```
CNN/
├── cloud/                          # 云端 FastAPI 后端
│   ├── venv/                       # Python 虚拟环境（Windows）
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口 + 路由注册 + WebSocket
│   │   ├── lifespan.py             # 生命周期 + 后台分析 worker + 线程池
│   │   ├── startup.py              # 数据库初始化 + 默认设备创建
│   │   ├── middleware.py           # CORS / 静态文件挂载
│   │   ├── database.py             # SQLite/MySQL 连接
│   │   ├── models.py               # SQLAlchemy 数据模型
│   │   ├── core/config.py          # 全局配置（端口、采样率、NN开关）
│   │   ├── api/
│   │   │   ├── data_view/          # 实时频谱计算（FFT/STFT/包络/阶次/倒谱/统计）
│   │   │   │   ├── __init__.py     # router + 公共函数
│   │   │   │   ├── core.py         # 设备/批次/原始数据/删除
│   │   │   │   ├── spectrum.py     # FFT / STFT / 统计
│   │   │   │   ├── envelope.py     # 包络谱
│   │   │   │   ├── order.py        # 阶次跟踪
│   │   │   │   ├── cepstrum.py     # 倒谱
│   │   │   │   ├── gear.py         # 齿轮诊断 + 全分析
│   │   │   │   ├── export.py       # CSV 导出
│   │   │   │   └── diagnosis_ops.py # 诊断更新 + 重新诊断
│   │   │   ├── ingest.py           # 边端数据接入
│   │   │   ├── dashboard.py        # 设备总览 + 离线检测
│   │   │   ├── diagnosis.py        # 诊断结果查询
│   │   │   ├── alarms.py           # 告警管理
│   │   │   ├── devices/            # 设备配置
│   │   │   │   ├── __init__.py     # router + 公共导入
│   │   │   │   ├── core.py         # 设备 CRUD
│   │   │   │   └── config.py       # 通道参数、告警阈值、机械参数
│   │   │   ├── collect.py          # 手动采集任务
│   │   │   └── system.py           # 系统日志（journalctl）
│   │   └── services/
│   │       ├── analyzer.py         # 分析引擎（多通道综合分析）
│   │       ├── alarms/             # 告警生成逻辑
│   │       │   ├── __init__.py     # 统一导出 generate_alarms
│   │       │   ├── channel.py      # 通道级振动特征告警
│   │       │   ├── device.py       # 设备级综合告警
│   │       │   └── diagnosis.py    # 诊断结果告警
│   │       ├── diagnosis/          # 诊断算法库
│   │       │   ├── engine.py       # DiagnosisEngine 主类（调度器）
│   │       │   ├── health_score.py # 综合健康度评分
│   │       │   ├── recommendation.py # 诊断建议生成
│   │       │   ├── bearing.py      # 轴承诊断（包络/Kurtogram/CPW/MED）
│   │       │   ├── gear/           # 齿轮诊断
│   │       │   │   ├── __init__.py # 齿轮诊断公共接口
│   │       │   │   └── metrics.py  # FM0/FM4/CAR/M6A/M8A/SER 指标
│   │       │   ├── preprocessing.py# 小波去噪 / CPW / MED
│   │       │   ├── vmd_denoise.py  # VMD 变分模态分解
│   │       │   ├── features.py     # 时域/频域/阶次/包络特征提取
│   │       │   ├── rule_based.py   # 规则诊断算法（回退方案）
│   │       │   ├── order_tracking.py # 阶次跟踪算法（单帧/多帧/变速）
│   │       │   └── signal_utils.py # 通用信号处理辅助函数
│   │       └── nn_predictor.py     # 【神经网络预留接口】
│   ├── models/                     # 模型文件存放目录
│   ├── turbine.db                  # SQLite 数据库（自动生成）
│   ├── requirements.txt
│   └── .env                        # 环境变量配置
│
├── wind-turbine-diagnosis/         # Vue3 前端
│   ├── node_modules/
│   ├── src/
│   │   ├── api/index.js            # API 封装
│   │   ├── utils/request.js        # Axios 工具
│   │   └── views/                  # 页面组件
│   ├── vite.config.js              # 代理配置（固定到 8.137.96.104:8000）
│   └── package.json
│
├── edge/                           # 边端 Python 采集脚本
│   ├── venv/                       # Python 虚拟环境
│   ├── edge_client.py              # 主程序（采集 + 上传）
│   ├── signal_generator.py         # 信号生成器（模拟/真实.npy）
│   ├── compressor.py               # 数据压缩（降采样 + msgpack + zlib）
│   ├── requirements.txt
│   └── .env                        # 边端配置
│
└── tests/                          # 回归测试
    └── diagnosis/
        ├── test_none_params.py     # None 参数安全测试
        ├── test_cpw_robustness.py  # CPW 鲁棒性测试
        └── test_varying_speed_order.py # 变速阶次跟踪测试
```

---

## 3. 虚拟环境激活

**⚠️ 重要：每个 Python 模块有独立的 venv，执行任何 Python 命令前必须先激活对应 venv。**

### 3.1 本地 Windows

```bash
# 云端后端（cloud）
 cd /d/code/CNN/cloud
 . venv/Scripts/activate

# 边端（edge）
 cd /d/code/CNN/edge
 . venv/Scripts/activate
```

> **Windows 下不使用 `source`，使用 `. venv/Scripts/activate`**

### 3.2 服务器 Ubuntu

```bash
# 后端
 cd /opt/CNN/cloud
 source venv/bin/activate

# 边端（如果在服务器上运行）
 cd /opt/CNN/edge
 source venv/bin/activate
```

---

## 4. 开发命令

### 4.1 云端后端（cloud）

```bash
 cd /d/code/CNN/cloud
 . venv/Scripts/activate

# 安装依赖
 pip install -r requirements.txt

# 启动开发服务器（带热重载）
 python -m app.main
# 或
 uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# API 文档
# http://localhost:8000/docs （Swagger UI）
```

### 4.2 前端（wind-turbine-diagnosis）

```bash
 cd /d/code/CNN/wind-turbine-diagnosis

# 安装依赖（首次）
 npm install

# 启动开发服务器
 npm run dev
# 浏览器自动打开 http://localhost:3000

# 构建生产包
 npm run build
# 输出到 dist/ 目录
```

**代理配置注意：**

- `vite.config.js` 中 `/api` 和 `/ws` 固定代理到 `http://8.137.96.104:8000`
- **不要修改此配置**，前端打包后部署到服务器时靠 Nginx 反向代理

### 4.3 边端（edge）

```bash
 cd /d/code/CNN/edge
 . venv/Scripts/activate

# 安装依赖
 pip install -r requirements.txt

# 启动采集客户端
 python edge_client.py
```

### 4.4 一键启动（Windows）

```bash
# 在项目根目录
cd /d/code/CNN
start.bat
```

---

## 5. 测试

```bash
 cd /d/code/CNN/cloud
 . venv/Scripts/activate

# 运行全部诊断回归测试
 python ../tests/diagnosis/test_none_params.py
 python ../tests/diagnosis/test_cpw_robustness.py
 python ../tests/diagnosis/test_varying_speed_order.py

# 验证语法
 python -c "import ast; ast.parse(open('app/main.py', encoding='utf-8').read())"
 python -c "import ast; ast.parse(open('app/api/data_view/__init__.py', encoding='utf-8').read())"

# 验证 FastAPI 可导入
 python -c "from app.main import app; print('OK')"
```

---

## 6. 线程与内存限制（2G 服务器关键）

**服务器配置：2核 CPU + 2GB 内存**

### 6.1 全局线程池限制

`cloud/app/lifespan.py` 在 lifespan 中创建：**`ThreadPoolExecutor(max_workers=2)`**，并设为 asyncio 默认 executor。

- 所有 `asyncio.to_thread()` 调用复用此线程池
- 后台分析 + DataView 实时计算共享这 2 个线程
- **绝对不要增加 max_workers**，否则可能 OOM

### 6.2 后台分析串行化

```python
ANALYSIS_SEM = asyncio.Semaphore(1)
```

后台分析 worker 一次只分析一个批次，即使多个设备有待分析数据也排队执行。

### 6.3 DataView 实时计算

以下接口已改为 `async def`，核心计算放入线程池：

- `/api/data/{...}/stft`
- `/api/data/{...}/envelope`
- `/api/data/{...}/order`
- `/api/data/{...}/cepstrum`
- `/api/data/{...}/gear`
- `/api/data/{...}/analyze`

计算快的接口保持 `def`（FastAPI 自动用 anyio 线程池）：FFT、统计指标、原始数据查询等。

### 6.4 信号长度截断

所有 DataView 实时计算接口限制最多处理 **5 秒数据**：

```python
max_samples = sample_rate * 5
if len(signal) > max_samples:
    signal = signal[:max_samples]
```

---

## 7. 关键配置

### 7.1 后端 `cloud/.env`

```env
USE_SQLITE=true              # true=SQLite(默认), false=MySQL
API_HOST=0.0.0.0
API_PORT=8000
SENSOR_SAMPLE_RATE=25600     # 默认采样率
SENSOR_WINDOW_SECONDS=10     # 采集时长
NN_ENABLED=false             # 神经网络开关
ADMIN_PASSWORD=admin123      # 网页登录密码
SECRET_KEY=change-me-in-production-please
EDGE_API_KEY=turbine-edge-secret
```

### 7.2 边端 `edge/.env`

```env
CLOUD_INGEST_URL=http://localhost:8000/api/ingest/
DEVICE_IDS=WTG-001,WTG-002,WTG-003,WTG-004,WTG-005
USE_REAL_DATA=true
DATA_DIR=D:\code\wavelet_study\dataset\HUSTbear\down8192
SAMPLE_RATE=8192
DURATION=10
COMPRESSION_ENABLED=true
DOWNSAMPLE_RATIO=8
```

### 7.3 前端代理 `wind-turbine-diagnosis/vite.config.js`

```javascript
proxy: {
  '/api': { target: 'http://8.137.96.104:8000', changeOrigin: true },
  '/ws':  { target: 'ws://8.137.96.104:8000',  ws: true, changeOrigin: true }
}
```

**禁止修改** — 前端打包后由 Nginx 反向代理到后端。

---

## 8. 诊断引擎关键代码路径

### 8.1 诊断策略调度器

```
cloud/app/services/diagnosis/engine.py
```

- `DiagnosisEngine` 类：轴承/齿轮/综合分析入口（调度器）
- `preprocess()`: wavelet / VMD 去噪
- `analyze_bearing()`: 调用 bearing.py 中的具体算法
- `analyze_gear()`: 调用 gear/ 中的具体算法
- `analyze_comprehensive()`: 综合分析（轴承 + 齿轮 + 时域特征）

### 8.2 健康度评分与建议

```
cloud/app/services/diagnosis/health_score.py
cloud/app/services/diagnosis/recommendation.py
```

- `_compute_health_score()`: 综合健康度评分 (0-100)
- `_generate_recommendation()`: 根据故障指示器生成维护建议

### 8.3 阶次跟踪算法

```
cloud/app/services/diagnosis/order_tracking.py
```

- `_compute_order_spectrum()`: 单帧阶次跟踪（恒定转速）
- `_compute_order_spectrum_multi_frame()`: 多帧平均（转速缓变）
- `_compute_order_spectrum_varying_speed()`: 变速跟踪（STFT + 等相位重采样）

### 8.4 轴承诊断

```
cloud/app/services/diagnosis/bearing.py
```

- `envelope_analysis()`: 标准包络谱
- `fast_kurtogram()`: Fast Kurtogram 自适应频带选择
- `cpw_envelope_analysis()`: 倒频谱预白化 + 包络
- `med_envelope_analysis()`: 最小熵解卷积 + 包络

### 8.5 齿轮诊断指标

```
cloud/app/services/diagnosis/gear/metrics.py
```

- `compute_fm0_order()`: 粗故障检测
- `compute_fm4()`: 局部故障检测
- `compute_car()`: 倒频谱幅值比
- `compute_ser_order()`: 边频带能量比

### 8.6 后台分析入口

```
cloud/app/services/analyzer.py
```

- `analyze_device()`: 多通道综合分析（被 lifespan.py 后台 worker 调用）
- 特征计算已移至 `cloud/app/services/diagnosis/features.py`
- 规则诊断已移至 `cloud/app/services/diagnosis/rule_based.py`

---

## 9. 数据集

**HUSTbear 轴承数据集：**

- 路径：`D:\code\wavelet_study\dataset\HUSTbear\down8192`
- 采样率：8192 Hz
- 文件格式：`.npy`（NumPy 一维数组，`dtype=float64`）
- 文件命名规则：`{负载}_{故障类型}_{转速模式}-{通道}.npy`
  - 负载：`0.5X` / `1X` / `1.5X` / `2X`（负载比例）
  - 故障类型：`N`（健康）/ `B`（球故障）/ `IR`（内圈）/ `OR`（外圈）/ `C`（复合）
  - 转速模式：`CS`（恒定转速）/ `VS`（变速，如 `0_40_0Hz` 表示 0→40→0 Hz 扫频）
  - 通道：`X` / `Y` / `Z`（三轴加速度计方向）
- 数据示例：`0.5X_B_VS_0_40_0Hz-X.npy`
  - 0.5 倍负载，球故障，变速 0-40-0Hz，X 方向通道
- 数据长度：每文件约 5~10 秒振动信号（40960~81920 点 @ 8192Hz）
- 用途：边端真实数据模式读取 `.npy` 文件，按批次上传至云端诊断

---

## 10. 数据库表

| 表名 | 用途 |
|------|------|
| `devices` | 设备信息、健康度、配置参数 |
| `sensor_data` | 传感器原始数据（普通 batch 1~16 循环覆盖，特殊 batch ≥101 永久保留） |
| `diagnosis` | 诊断结果（关联 batch_index），支持按通道和去噪方法分版本缓存 |
| `alarms` | 告警记录（通道级 + 设备级） |
| `collection_tasks` | 手动采集任务 |

### 10.1 诊断结果表（`diagnosis`）字段详情

| 字段 | 类型 | 说明 |
|------|------|------|
| `device_id` | `VARCHAR(50)` | 设备编号 |
| `batch_index` | `INTEGER` | 关联的 sensor_data 批次号 |
| `channel` | `INTEGER` | 通道号（1/2/3...），默认 0 表示批次级 |
| `health_score` | `INTEGER` | 综合健康度 0-100 |
| `fault_probabilities` | `JSON` | 各故障类型概率分布 |
| `imf_energy` | `JSON` | IMF 能量分布 |
| `order_analysis` | `JSON` | 阶次/包络/频谱分析明细 |
| `rot_freq` | `FLOAT` | 估计转频 Hz |
| `status` | `VARCHAR(20)` | 综合状态：normal/warning/critical |
| `engine_result` | `JSON` | `/analyze` 综合分析完整结果（通道级） |
| `full_analysis` | `JSON` | `/full-analysis` 全算法分析完整结果（通道级） |
| `denoise_method` | `VARCHAR(20)` | 去噪方法：none/wavelet/vmd/med |
| `analyzed_at` | `DATETIME` | 分析时间 |

### 10.2 诊断缓存策略

DataView 实时计算端点（`/analyze`、`/full-analysis`）执行完成后会自动将结果写入 `diagnosis` 表。缓存键为 `(device_id, batch_index, channel, denoise_method)`：

- **同一设备、同一批次、同一通道、同一去噪方法**的结果会被覆盖更新
- **不同去噪方法**的结果独立保存，互不覆盖
- 前端 `GET /api/data/{device_id}/{batch_index}/{channel}/diagnosis?denoise_method=xxx` 优先返回精确匹配的缓存
- 若未指定 `denoise_method`，或精确匹配无结果，则回退到该通道最新诊断记录
- 旧数据（无 `denoise_method` 字段）仍可通过批次级回退查询兼容读取

**查询优先级：**
1. 精确匹配 `device + batch + channel + denoise_method`
2. 该通道最新结果（不限去噪方法）
3. 批次级诊断记录（兼容旧数据）

---

## 11. 编码规范

- **Python**：UTF-8 编码，所有文件含中文注释
- **字符串替换**：使用 `StrReplaceFile` 工具，不要用 Shell `sed`
- **路径**：Windows 用 `/` 或 `\`，Shell 命令中用 Unix 风格 `/`
- **虚拟环境命令**：Windows `. venv/Scripts/activate`，Ubuntu `source venv/bin/activate`
- **线程安全**：2G 服务器严禁增加线程池大小

---

## 12. 常见问题速查

| 问题 | 解决 |
|------|------|
| `ModuleNotFoundError` | 检查是否在对应 venv 中，是否 `pip install -r requirements.txt` |
| 后端 HTTP 超时 | 检查 journalctl 日志，`asyncio.to_thread` 是否正常工作 |
| 阶次谱和诊断结果不一致 | 检查 `analyzer.py` 和 `data_view/order.py` 是否调用同一套 `order_tracking.py` 函数 |
| 前端空白 | 检查 `npm install` 是否完成，代理是否连通 |
| 内存不足 OOM | 检查线程池是否超过 2 个，信号是否截断到 5 秒 |
| 数据清空 | 删除 `cloud/turbine.db`，重启后端 |
