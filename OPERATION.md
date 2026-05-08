# 风机齿轮箱智能故障诊断系统 — 操作手册

> 本文档只讲操作，不讲原理。按步骤执行即可。

---

## 一、环境准备

### 1.1 确认已安装

| 软件 | 最低版本 | 验证命令 |
|------|---------|---------|
| Node.js | 18 | `node -v` |
| Python | 3.9 | `python --version` |

如果未安装，先去官网下载：
- Node.js：https://nodejs.org/ （下载 LTS 版）
- Python：https://www.python.org/downloads/

> 不需要 Docker，不需要安装 MySQL。

---

## 二、启动后端服务

### 2.1 进入后端目录

```bash
cd cloud
```

### 2.2 创建 Python 虚拟环境（推荐）

```bash
python -m venv venv
```

### 2.3 激活虚拟环境

**Windows：**
```bash
venv\Scripts\activate
```

**macOS / Linux：**
```bash
source venv/bin/activate
```

> 激活成功后，命令行前会出现 `(venv)` 字样。

### 2.4 安装依赖

```bash
pip install -r requirements.txt
```

### 2.5 启动服务

```bash
python -m app.main
```

看到以下输出即表示启动成功：
```
[启动] 初始化数据库...
[启动] 创建设备: WTG-001
[启动] 后台分析任务已启动
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**验证：** 浏览器打开 http://localhost:8000/docs ，能看到 API 文档页面。

> 第一次启动会自动创建 `cloud/turbine.db`（SQLite 数据库文件）。
> 
> **保持此终端运行，不要关闭。**

---

## 三、启动边端采集（可选）

> 不启动边端，系统也能正常运行（会用默认数据初始化）。启动后会有动态数据持续流入。

### 3.1 新开一个终端，进入边端目录

```bash
cd edge
```

### 3.2 创建并激活虚拟环境

```bash
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS/Linux
```

### 3.3 安装依赖

```bash
pip install -r requirements.txt
```

### 3.4 启动采集器

```bash
python edge_client.py
```

看到以下输出即表示正常运行：
```
风机边端数据采集客户端
设备: WTG-001
目标: http://localhost:8000/api/ingest/
频率: 每 5 秒上传一批
```

> **保持此终端运行，不要关闭。**

---

## 四、启动前端界面

### 4.1 新开一个终端，进入前端目录

```bash
cd wind-turbine-diagnosis
```

### 4.2 安装依赖（首次需要）

```bash
npm install
```

### 4.3 启动开发服务器

```bash
npm run dev
```

浏览器会自动打开 http://localhost:3000

> **保持此终端运行，不要关闭。**

---

## 五、界面操作说明

### 5.1 Dashboard（设备总览）

| 功能 | 说明 |
|------|------|
| 设备状态卡片 | 显示运行状态、健康度评分、运行时长、告警数量 |
| 健康度仪表盘 | 圆形仪表，0-100 分，蓝色指针 |
| 故障类型分布 | 环形饼图，展示历史故障占比 |
| 部件状态表格 | 6 个关键部件的健康度和状态标签 |

### 5.2 Monitor（实时监测）

| 功能 | 说明 |
|------|------|
| 开始/暂停监测 | 点击右上角按钮控制数据刷新 |
| 传感器状态 | 6 个传感器的指示灯（正常为绿色） |
| 运行参数 | 转速、温度、负载的实时数值 |
| 时域波形图 | 振动信号的时间序列波形，每 2 秒自动刷新 |
| 频域谱图 | 振动信号的频率分布 |
| 通道切换 | 图表右上角下拉框切换 3 个通道 |

### 5.3 Diagnosis（故障诊断）

| 功能 | 说明 |
|------|------|
| 诊断结果概要 | 诊断时间、故障数量、整体状态标签 |
| 故障详情卡片 | 每个故障的部件、类型、置信度、严重程度 |
| IMF 分解能量 | 柱状图，展示 5 个 IMF 分量的能量占比 |
| 故障概率分布 | 横向柱状图，各故障类型的概率百分比 |

### 5.4 Alarm（告警管理）

| 功能 | 说明 |
|------|------|
| 统计卡片 | 严重告警数、预警数、已处理数 |
| 告警列表 | 分页表格，展示所有历史告警 |
| 刷新按钮 | 右上角重新拉取最新告警 |
| 查看详情 | 点击"查看详情"弹出详细信息对话框 |

---

## 六、配置修改

### 6.1 后端配置（`cloud/.env`）

```
# 数据库切换
USE_SQLITE=true              # true=SQLite(默认), false=MySQL

# 如果切换 MySQL，填写以下信息
DB_HOST=localhost
DB_PORT=3306
DB_USER=turbine
DB_PASSWORD=turbine1234
DB_NAME=turbine_db

# 服务端口
API_PORT=8000

# 神经网络开关
NN_ENABLED=false             # true=启用模型预测
NN_MODEL_PATH=./models/turbine_fault_model.onnx
```

> 修改 `.env` 后需要**重启后端**才能生效。

### 6.2 边端配置（`edge/.env`）

```
CLOUD_INGEST_URL=http://localhost:8000/api/ingest/
DEVICE_ID=WTG-001
UPLOAD_INTERVAL=5            # 上传间隔，单位秒
```

---

## 七、接入神经网络模型

### 7.1 准备模型文件

训练好的模型导出为以下任一格式：
- ONNX（推荐，跨框架）
- PyTorch TorchScript（`.pt`）
- TensorFlow SavedModel / HDF5

### 7.2 放置模型

```bash
# 把模型文件复制到
cloud/models/turbine_fault_model.onnx
```

### 7.3 启用模型

编辑 `cloud/.env`：
```
NN_ENABLED=true
NN_MODEL_PATH=./models/turbine_fault_model.onnx
```

### 7.4 实现推理代码

打开 `cloud/app/services/nn_predictor.py`，找到 `predict()` 和 `_load_model()` 函数，按你使用的框架取消对应注释并修改：

**ONNX Runtime 示例：**
```python
import onnxruntime as ort

# _load_model() 中：
_model = ort.InferenceSession(NN_MODEL_PATH)

# predict() 中：
input_name = model.get_inputs()[0].name
outputs = model.run(None, {input_name: input_tensor.reshape(1, -1)})
probs = outputs[0][0]
```

**PyTorch 示例：**
```python
import torch

# _load_model() 中：
_model = torch.jit.load(NN_MODEL_PATH)
_model.eval()

# predict() 中：
with torch.no_grad():
    x = torch.from_numpy(input_tensor).unsqueeze(0)
    probs = torch.softmax(model(x), dim=1).numpy()[0]
```

### 7.5 重启后端

```bash
# 在 cloud 目录下
python -m app.main
```

控制台会输出 `[NN] ONNX 模型加载成功` 或 `[NN] 模型已加载，但推理代码尚未实现`。

> 如果模型加载失败，系统**不会崩溃**，自动回退到简化规则算法继续运行。

---

## 八、切换 MySQL（可选）

如果 SQLite 不满足需求（如多机部署、数据量极大），可切换为 MySQL。

### 8.1 安装 MySQL

- Windows：下载 [MySQL Installer](https://dev.mysql.com/downloads/installer/) 安装
- 或使用 [XAMPP](https://www.apachefriends.org/)

### 8.2 创建数据库和用户

用 MySQL 客户端（如 Navicat、DBeaver、或命令行）执行：

```sql
CREATE DATABASE turbine_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'turbine'@'%' IDENTIFIED BY 'turbine1234';
GRANT ALL PRIVILEGES ON turbine_db.* TO 'turbine'@'%';
FLUSH PRIVILEGES;
```

### 8.3 安装 PyMySQL

```bash
cd cloud
pip install pymysql cryptography
```

### 8.4 修改配置

编辑 `cloud/.env`：
```
USE_SQLITE=false
DB_HOST=localhost
DB_PORT=3306
DB_USER=turbine
DB_PASSWORD=turbine1234
DB_NAME=turbine_db
```

### 8.5 重启后端

```bash
python -m app.main
```

数据库表会自动创建。

---

## 九、停止系统

按 **Ctrl + C** 依次关闭：
1. 前端终端（`npm run dev`）
2. 边端终端（`python edge_client.py`，如已启动）
3. 后端终端（`python -m app.main`）

---

## 十、常见问题速查

| 现象 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError` | 没在虚拟环境中 / 依赖没装 | 执行 `venv\Scripts\activate` 再 `pip install -r requirements.txt` |
| `Connection refused`（边端） | 后端没启动 | 先启动 `python -m app.main` |
| 前端页面空白 | 后端未启动 / 依赖未装 | 确认后端运行中；前端执行 `npm install` |
| 健康度始终不变 | 边端没启动 | 启动 `python edge_client.py` 产生动态数据 |
| 模型加载失败 | 路径错误 / 缺少推理库 | 检查 `NN_MODEL_PATH`；安装 `onnxruntime` 或 `torch` |
| 想清空所有数据 | — | SQLite：删除 `cloud/turbine.db` 后重启后端 |
