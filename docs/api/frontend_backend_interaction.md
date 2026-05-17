# 前后端交互详细映射文档

> **文档用途**：建立前端 Vue 组件与后端 FastAPI 端点之间的完整映射关系，让 AI Agent 在修改 API 时能同步知道哪些前端组件会受影响。
>
> **维护提醒**：
>
> - 新增或修改 API 端点时，必须同步更新本文档
> - 修改 `async` 状态或请求/响应结构时，需检查前端对应调用点
> - 本文档按功能模块分组，便于快速定位影响范围

---

## 目录

1. [认证 (Auth)](#1-认证-auth)
2. [Dashboard](#2-dashboard)
3. [数据查看 (DataView)](#3-数据查看-dataview)
4. [高级诊断 (ResearchDiagnosis)](#4-高级诊断-researchdiagnosis)
5. [实时监测 (Monitor)](#5-实时监测-monitor)
6. [告警 (Alarm)](#6-告警-alarm)
7. [系统设置 (Settings)](#7-系统设置-settings)
8. [日志 (Logs)](#8-日志-logs)
9. [边端 (Edge)](#9-边端-edge)

---

## 1. 认证 (Auth)

| 前端调用点 | API 函数 | HTTP 方法 + URL | 后端处理函数 | 说明 |
|-----------|---------|----------------|-------------|------|
| `Login.vue` → 登录提交 | `api/index.js::login(password)` | `POST /api/auth/login` | `auth.py::login` | ⚠️ 影响前端：返回 JWT Token，前端存入 `localStorage` |
| `request.js` → 请求拦截器 | — | 自动注入 `Authorization: Bearer <token>` | — | 所有 HTTP 请求自动携带 Token |
| `request.js` → 响应拦截器 | — | 处理 `401 Unauthorized` | — | ⚠️ 影响前端：Token 过期或无效时自动跳转登录页 |

---

## 2. Dashboard

| 前端调用点 | API 函数 | HTTP 方法 + URL | 后端处理函数 | 说明 |
|-----------|---------|----------------|-------------|------|
| `Dashboard.vue::loadData()` | `api/index.js::getDeviceInfo()` | `GET /api/dashboard/` | `dashboard.py::get_dashboard` | 获取设备总览信息 |
| `Dashboard.vue` → WebSocket | — | `WS /ws/monitor` | `main.py` WebSocket 端点 | 🌐 WebSocket 推送：`device_online`, `device_offline` |

---

## 3. 数据查看 (DataView)

| 前端调用点 | API 函数 | HTTP 方法 + URL | 后端处理函数 | 说明 |
|-----------|---------|----------------|-------------|------|
| `DataView.vue::loadAllDevices()` | `api/data.js::getAllDeviceData()` | `GET /api/data/devices` | `data_view/core.py::get_all_device_data` | 加载所有设备及批次列表 |
| `DataView.vue::selectBatch()` | `api/data.js::getChannelData()` | `GET /api/data/{id}/{batch}/{ch}` | `data_view/core.py::get_channel_data` | 获取指定通道原始波形数据 |
| `DataView.vue::computeFFT()` | `api/data.js::getChannelFFT()` | `GET /api/data/{id}/{batch}/{ch}/fft` | `data_view/spectrum.py::get_channel_fft` | 计算 FFT 频谱 |
| `DataView.vue::computeSTFT()` | `api/data.js::getChannelSTFT()` | `GET /api/data/{id}/{batch}/{ch}/stft` | `data_view/spectrum.py::get_channel_stft` | ⏳ async：计算 STFT 时频图 |
| `DataView.vue::computeEnvelope()` | `api/data.js::getChannelEnvelope()` | `GET /api/data/{id}/{batch}/{ch}/envelope` | `data_view/envelope.py::get_channel_envelope` | ⏳ async：计算包络谱 |
| `DataView.vue::computeOrder()` | `api/data.js::getChannelOrder()` | `GET /api/data/{id}/{batch}/{ch}/order` | `data_view/order.py::get_channel_order` | ⏳ async：计算阶次跟踪谱 |
| `DataView.vue::computeCepstrum()` | `api/data.js::getChannelCepstrum()` | `GET /api/data/{id}/{batch}/{ch}/cepstrum` | `data_view/cepstrum.py::get_channel_cepstrum` | ⏳ async：计算倒频谱 |
| `DataView.vue::computeGear()` | `api/data.js::getChannelGear()` | `GET /api/data/{id}/{batch}/{ch}/gear` | `data_view/gear.py::get_channel_gear` | ⏳ async：齿轮诊断分析 |
| `DataView.vue::computeFullAnalysis()` | `api/data.js::getChannelFullAnalysis()` | `GET /api/data/{id}/{batch}/{ch}/full-analysis` | `data_view/gear.py::get_channel_full_analysis` | ⏳ async：全算法综合分析 |
| `DataView.vue::computeStrategyAnalyze()` | `api/data.js::getChannelAnalyze()` | `GET /api/data/{id}/{batch}/{ch}/analyze` | `data_view/gear.py::get_channel_analyze` | ⏳ async：策略分析（综合诊断） |
| `DataView.vue::computeStats()` | `api/data.js::getChannelStats()` | `GET /api/data/{id}/{batch}/{ch}/stats` | `data_view/spectrum.py::get_channel_stats` | 计算时域统计指标 |
| `DataView.vue::onReanalyze()` | `api/data.js::reanalyzeBatch()` | `POST /api/data/{id}/{batch}/reanalyze` | `data_view/diagnosis_ops.py::reanalyze_batch` | ⏳ async：单批次重新诊断 |
| `DataView.vue::onReanalyzeAll()` | `api/data.js::reanalyzeAllDevice()` | `POST /api/data/{id}/reanalyze-all` | `data_view/diagnosis_ops.py::reanalyze_all_batches` | ⏳ async：全部批次重新诊断 |
| `DataView.vue::onDeleteBatch()` | `api/data.js::deleteBatch()` | `DELETE /api/data/{id}/{batch}` | `data_view/core.py::delete_batch` | 删除指定批次数据 |
| `DataView.vue::exportChannelCSV()` | `window.open()` 直接打开 | `GET /api/data/{id}/{batch}/{ch}/export` | `data_view/export.py::export_channel_csv` | 导出通道数据为 CSV 文件 |
| `DataView.vue::gotoResearchDiagnosis()` | — | 路由跳转带 query 参数 | — | 跳转到高级诊断页面，携带设备/批次/通道参数 |

> **⚠️ 影响前端**：`DataView.vue` 是核心数据查看组件，任何 `/api/data/{id}/{batch}/{ch}/*` 端点的 URL 变更、参数增减或响应结构调整，都需要同步修改 `frontend/src/views/DataView.vue` 和 `frontend/src/api/data.js`。

---

## 4. 高级诊断 (ResearchDiagnosis)

| 前端调用点 | API 函数 | HTTP 方法 + URL | 后端处理函数 | 说明 |
|-----------|---------|----------------|-------------|------|
| `ResearchDiagnosis.vue::loadDevices()` | `api/data.js::getAllDeviceData()` | `GET /api/data/devices` | `data_view/core.py::get_all_device_data` | 加载设备列表（复用 DataView API） |
| `ResearchDiagnosis.vue::loadMethodInfo()` | `api/data.js::getMethodInfo()` | `GET /api/data/method-info` | `data_view/research.py::get_method_info` | 获取可用分析方法列表 |
| `ResearchDiagnosis.vue::runAnalysis()` | `api/data.js::getChannelMethodAnalysis()` | `GET /api/data/{id}/{batch}/{ch}/method-analysis` | `data_view/research.py` | ⏳ async：指定方法单分析 |
| `ResearchDiagnosis.vue::runAnalysis()` | `api/data.js::getChannelResearchAnalysis()` | `GET /api/data/{id}/{batch}/{ch}/research-analysis` | `data_view/research.py` | ⏳ async：研究模式多方法对比分析 |

> **⚠️ 影响前端**：`ResearchDiagnosis.vue` 依赖 `method-info` 返回的方法元数据来动态渲染分析选项，修改方法列表结构需同步前端。

---

## 5. 实时监测 (Monitor)

| 前端调用点 | API 函数 | HTTP 方法 + URL | 后端处理函数 | 说明 |
|-----------|---------|----------------|-------------|------|
| `Monitor.vue::loadLatestData()` | `api/index.js::getRealtimeVibrationData()` | `GET /api/monitor/latest` | `monitor.py::get_latest_monitor` | 获取最新监测数据 |
| `Monitor.vue::loadHistory()` | `api/index.js::getMonitorHistory()` | `GET /api/monitor/history` | `monitor.py::get_monitor_history` | 获取某通道最近N批次历史数据 |
| `Monitor.vue::requestCollect()` | `api/system.js::requestCollection()` | `POST /api/collect/request` | `collect.py::request_collection` | 发起手动采集任务 |
| `Monitor.vue::startPolling()` | `api/system.js::getTaskStatus()` | `GET /api/collect/tasks/{id}/status` | `collect.py::get_task_status` | 轮询采集任务状态 |
| 待接入页面 | `api/system.js::getCollectionHistory()` | `GET /api/collect/history` | `collect.py::get_collection_history` | 查询采集历史记录 |
| `Monitor.vue` → WebSocket | — | `WS /ws/monitor` | `main.py` WebSocket 端点 | 🌐 WebSocket 推送：`sensor_update`, `diagnosis_update` |

> **⚠️ 影响前端**：`Monitor.vue` 同时依赖 HTTP 轮询和 WebSocket 推送，修改推送消息格式需同步前端 WebSocket 处理器。

---

## 6. 告警 (Alarm)

| 前端调用点 | API 函数 | HTTP 方法 + URL | 后端处理函数 | 说明 |
|-----------|---------|----------------|-------------|------|
| `Alarm.vue::loadData()` | `api/alarm.js::getHistoryAlarmList()` | `GET /api/alarms/` | `alarms.py::get_alarms` | 获取告警历史列表 |
| `Alarm.vue::handleResolve()` | `api/alarm.js::updateAlarmStatus()` | `POST /api/alarms/{id}/resolve` | `alarms.py::resolve_alarm` | 将告警标记为已处理 |
| `Alarm.vue::handleDelete()` | `api/alarm.js::deleteAlarm()` | `DELETE /api/alarms/{id}` | `alarms.py::delete_alarm` | 删除告警记录 |
| `Alarm.vue::loadDeviceList()` | `api/device.js::getDevices()` | `GET /api/devices/` | `devices/core.py::get_devices` | 加载设备列表用于筛选 |

> **⚠️ 影响前端**：`Alarm.vue` 中告警状态流转（未处理 → 已处理）依赖响应数据实时更新列表。

---

## 7. 系统设置 (Settings)

| 前端调用点 | API 函数 | HTTP 方法 + URL | 后端处理函数 | 说明 |
|-----------|---------|----------------|-------------|------|
| `Settings.vue::loadDevices()` | `api/device.js::getDevices()` | `GET /api/devices/` | `devices/core.py::get_devices` | 加载设备列表 |
| `Settings.vue::onDeviceChange()` | `api/device.js::getDeviceConfig()` | `GET /api/devices/{id}/config` | `devices/config.py::get_device_config` | 获取指定设备配置 |
| `Settings.vue::onSaveEdgeConfig()` | `api/device.js::updateDeviceConfig()` | `PUT /api/devices/{id}/config` | `devices/config.py::update_device_config` | 保存边端采集配置 |
| `Settings.vue::onSaveMechanical()` | `api/device.js::updateDeviceConfig()` | `PUT /api/devices/{id}/config` | `devices/config.py::update_device_config` | 保存机械参数（轴承/齿轮参数） |
| `Settings.vue::onSaveThresholds()` | `api/device.js::updateAlarmThresholds()` | `PUT /api/devices/{id}/alarm-thresholds` | `devices/config.py::update_alarm_thresholds` | 保存告警阈值 |

> **⚠️ 影响前端**：`Settings.vue` 中机械参数（轴承 `n/d/D`、齿轮齿数等）直接影响后端诊断引擎的 `skip_bearing` / `skip_gear` 逻辑，前端表单校验需与后端参数有效性校验保持一致。

---

## 8. 日志 (Logs)

| 前端调用点 | API 函数 | HTTP 方法 + URL | 后端处理函数 | 说明 |
|-----------|---------|----------------|-------------|------|
| `Logs.vue::fetchLogs()` | `api/system.js::getSystemLogs()` | `GET /api/logs/` | `system.py::get_logs` | 获取系统日志（journalctl） |

---

## 9. 边端 (Edge)

> 以下映射非前端 Vue 组件调用，但属于前后端交互的一部分，需记录以便完整理解数据流。

| 调用方 | API 函数 | HTTP 方法 + URL | 后端处理函数 | 说明 |
|--------|---------|----------------|-------------|------|
| `edge_client.py` | — | `POST /api/ingest/` | `ingest.py::ingest_data` | 边端上传压缩后的传感器数据 |
| `edge_client.py` | — | `GET /api/devices/edge/config?device_id=xxx` | `devices/config.py::get_edge_config` | 边端拉取设备配置 |
| `edge_client.py` | — | `GET /api/collect/tasks?device_id=xxx` | `collect.py::get_pending_tasks` | 边端查询待执行的采集任务 |
| `edge_client.py` | — | `POST /api/collect/tasks/{id}/complete` | `collect.py::complete_task` | 边端上报采集任务完成 |

> **⚠️ 注意**：`edge_client.py` 与 `ingest.py` 之间的数据格式（msgpack + zlib 压缩结构）变更时，必须同步修改边端 `compressor.py` 和后端 `ingest.py` 的解压逻辑。

---

## 图例说明

| 标记 | 含义 |
|------|------|
| ⏳ async | 后端端点为 `async def`，核心计算通过 `asyncio.to_thread()` 在线程池执行 |
| 🌐 WebSocket | 该模块依赖 WebSocket 实时推送，消息格式变更需同步前端 |
| ⚠️ 影响前端 | 修改该端点时，前端对应组件需要同步调整 |

---

## 快速索引：后端文件 → 前端影响范围

| 后端文件 | 受影响的前端组件 |
|---------|----------------|
| `auth.py` | `Login.vue`, `request.js` |
| `dashboard.py` | `Dashboard.vue` |
| `data_view/core.py` | `DataView.vue`, `ResearchDiagnosis.vue` |
| `data_view/spectrum.py` | `DataView.vue` |
| `data_view/envelope.py` | `DataView.vue` |
| `data_view/order.py` | `DataView.vue` |
| `data_view/cepstrum.py` | `DataView.vue` |
| `data_view/gear.py` | `DataView.vue` |
| `data_view/export.py` | `DataView.vue` |
| `data_view/diagnosis_ops.py` | `DataView.vue` |
| `data_view/research.py` | `ResearchDiagnosis.vue` |
| `monitor.py` | `Monitor.vue` |
| `collect.py` | `Monitor.vue`, `edge_client.py` |
| `alarms.py` | `Alarm.vue` |
| `devices/core.py` | `Alarm.vue`, `Settings.vue` |
| `devices/config.py` | `Settings.vue`, `edge_client.py` |
| `system.py` | `Logs.vue`, `Monitor.vue` |
| `ingest.py` | `edge_client.py` |

---

*文档生成时间：2026-05-17*
*维护者：AI Agent（修改 API 时请务必同步更新）*
