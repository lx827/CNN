# 后端 API 接口文档

> **文档用途**：完整记录云端 FastAPI 后端的所有 REST API 端点、WebSocket 接口、请求/响应参数及调用约束。
> **维护要求**：新增、修改或删除任何 API 端点时，必须同步更新本文档和 `AGENTS.md` 中的引用。

---

## 目录

1. [认证接口](#1-认证接口)
2. [Dashboard 总览](#2-dashboard-总览)
3. [设备管理](#3-设备管理)
4. [实时监测](#4-实时监测)
5. [数据采集任务](#5-数据采集任务)
6. [数据查看与诊断 (data_view)](#6-数据查看与诊断-data_view)
7. [告警管理](#7-告警管理)
8. [系统日志](#8-系统日志)
9. [边端数据接入](#9-边端数据接入)
10. [WebSocket 实时推送](#10-websocket-实时推送)

---

## 通用约定

### 基础 URL

- 开发环境：`http://localhost:8000`
- 生产环境：`http://8.137.96.104:8000`

### 响应格式

所有 REST API 统一返回：

```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

- `code=200` 表示成功，非 200 时前端会 `ElMessage.error` 提示
- `code=401` 表示登录过期，前端会清除 token 并跳转登录页

### 认证方式

| 场景 | 方式 | 头部 |
|------|------|------|
| 前端页面 | JWT Bearer Token | `Authorization: Bearer <token>` |
| 边端采集 | API Key | `X-Edge-Key: <EDGE_API_KEY>` |
| 部分公共接口 | 可选认证 | `optional_auth` 依赖，兼容以上两种 |

---

## 1. 认证接口

### 1.1 用户登录

```
POST /api/auth/login
```

**请求体** (`LoginRequest`)：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `password` | `string` | ✅ | 管理密码（默认 `admin123`） |

**响应** (`TokenResponse`)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `access_token` | `string` | JWT Token |
| `token_type` | `string` | 固定 `"bearer"` |

**调用方**：`views/Login.vue` → `api/index.js::login()`

**非路由公共函数**（`auth.py`）：

| 函数 | 签名 | 说明 |
|------|------|------|
| `create_access_token` | `create_access_token(data: dict, expires_delta: timedelta = None) -> str` | 生成JWT Token |
| `verify_token_string` | `verify_token_string(token: str) -> str` | 验证JWT字符串 |
| `get_current_user` | `get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str` | FastAPI依赖，提取当前用户 |
| `optional_auth` | `optional_auth(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)) -> str` | 兼容JWT和X-Edge-Key的认证依赖 |

---

## 2. Dashboard 总览

### 2.1 获取设备总览

```
GET /api/dashboard/
```

**参数**：无（仅需认证）

**响应** (`dict`)：

| 字段路径 | 类型 | 说明 |
|---------|------|------|
| `data.devices` | `List[Device]` | 全部设备列表及状态 |
| `data.diagnosis` | `List[Diagnosis]` | 最新诊断结果摘要 |
| `data.alarm_stats` | `dict` | 告警统计（按级别分组） |

**内部常量**：
- `VALID_FAULT_TYPES`：17 种有效故障类型白名单
- `BEARING_FAULT_MAP`：轴承频率指示器 → 中文故障名映射

**调用方**：`views/Dashboard.vue` → `api/index.js::getDeviceInfo()`

---

## 3. 设备管理

### 3.1 获取所有设备列表

```
GET /api/devices/
```

**响应** (`dict`)：

| 字段路径 | 类型 | 说明 |
|---------|------|------|
| `data` | `List[Device]` | 设备完整字段列表 |

**返回字段包含**：`id`, `device_id`, `name`, `location`, `channel_count`, `channel_names`, `sample_rate`, `window_seconds`, `health_score`, `status`, `runtime_hours`, `upload_interval`, `task_poll_interval`, `alarm_thresholds`, `gear_teeth`, `bearing_params`, `compression_enabled`, `downsample_ratio`, `is_online`, `last_seen_at`

**调用方**：`views/Settings.vue`, `views/Alarm.vue`, `views/Monitor.vue` → `api/device.js::getDevices()`

---

### 3.2 获取设备配置

```
GET /api/devices/{device_id}/config
```

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `device_id` | `string` | 设备编号 |

**响应**：设备完整配置（含 `gear_teeth`, `bearing_params`, `channel_names` 等）

**调用方**：`views/Settings.vue` → `api/device.js::getDeviceConfig(deviceId)`

---

### 3.3 更新设备配置

```
PUT /api/devices/{device_id}/config
```

**路径参数**：`device_id: string`

**请求体** (`dict`)：

| 可更新字段 | 类型 | 说明 |
|-----------|------|------|
| `upload_interval` | `int` | 自动采集上传间隔(秒) |
| `task_poll_interval` | `int` | 任务轮询间隔(秒) |
| `sample_rate` | `int` | 采样率 Hz |
| `window_seconds` | `int` | 采集窗口秒数 |
| `channel_count` | `int` | 通道数 |
| `channel_names` | `dict` | 通道名称映射 |
| `gear_teeth` | `dict` | 齿轮参数 |
| `bearing_params` | `dict` | 轴承参数 |
| `compression_enabled` | `int` | 压缩开关 (0/1) |
| `downsample_ratio` | `int` | 降采样压缩比 |

**调用方**：`views/Settings.vue` → `api/device.js::updateDeviceConfig(deviceId, payload)`

---

### 3.4 批量更新设备配置

```
PUT /api/devices/batch-config
```

**请求体** (`dict`)：同上，应用到所有设备

**响应**：`{ updated_count, updated_fields }`

**调用方**：`views/Settings.vue` → `api/device.js::updateBatchDeviceConfig(payload)`

---

### 3.5 获取边端运行配置

```
GET /api/devices/edge/config?device_id={device_id}
```

**查询参数**：`device_id: string`

**响应**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `device_id` | `string` | 设备编号 |
| `upload_interval` | `int` | 上传间隔 |
| `task_poll_interval` | `int` | 任务轮询间隔 |
| `sample_rate` | `int` | 采样率 |
| `window_seconds` | `int` | 窗口时长 |
| `channel_count` | `int` | 通道数 |
| `compression_enabled` | `int` | 压缩开关 |
| `downsample_ratio` | `int` | 降采样比 |

**调用方**：边端 `edge_client.py` 启动时拉取

---

### 3.6 获取告警阈值

```
GET /api/devices/{device_id}/alarm-thresholds
```

**响应**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `alarm_thresholds` | `dict` | 原始配置 |
| `effective_thresholds` | `dict` | 生效阈值（含默认值回退） |

**可配置指标**：`rms`, `peak`, `kurtosis`, `crest_factor`（每项含 `warning` / `critical` 两级）

**调用方**：`views/Settings.vue` → `api/device.js::getAlarmThresholds(deviceId)`

---

### 3.7 更新告警阈值

```
PUT /api/devices/{device_id}/alarm-thresholds
```

**请求体** (`dict`)：阈值配置对象

**调用方**：`views/Settings.vue` → `api/device.js::updateAlarmThresholds(deviceId, payload)`

---

## 4. 实时监测

### 4.1 获取最新监测数据

```
GET /api/monitor/latest?device_id={device_id}&prefer_special={prefer_special}&limit={limit}
```

**查询参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `device_id` | `string` | `"WTG-001"` | 设备编号 |
| `prefer_special` | `bool` | `false` | 优先取特殊采集批次 |
| `limit` | `int` | `3` | 返回通道数 |

**响应**：每条含 `data`（时域）、`fft_freq`、`fft_amp`、`channel_name` 等

**内部常量**：
- `TIME_DOMAIN_POINTS = 2560`（时域返回点数）
- `FFT_POINTS = 25600`（FFT用1秒数据）
- `FFT_MAX_FREQ = 5000`（FFT最高返回频率）

**调用方**：`views/Monitor.vue` → `api/index.js::getRealtimeVibrationData()`

---

### 4.2 获取历史监测数据

```
GET /api/monitor/history?device_id={device_id}&channel={channel}&batches={batches}&include_special={include_special}
```

**查询参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `device_id` | `string` | `"WTG-001"` | 设备编号 |
| `channel` | `int` | `1` | 通道号 |
| `batches` | `int` | `16` | 返回批次数量 |
| `include_special` | `bool` | `true` | 包含特殊批次 |

**调用方**：`views/Monitor.vue`

---

## 5. 数据采集任务

### 5.1 发起采集请求

```
POST /api/collect/request?device_id={device_id}&sample_rate={sample_rate}&duration={duration}
```

**查询参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `device_id` | `string` | — | 目标设备 |
| `sample_rate` | `int` | `25600` | 采样率 |
| `duration` | `int` | `10` | 采集时长(秒) |

**响应**：`{ task_id, status, sample_rate, duration, created_at }`

**调用方**：`views/Monitor.vue` → `api/system.js::requestCollection()`

---

### 5.2 边端轮询待执行任务

```
GET /api/collect/tasks?device_id={device_id}
```

**响应**：`{ has_task, task_id, device_id, sample_rate, duration }`

**调用方**：边端 `edge_client.py`

---

### 5.3 标记任务完成

```
POST /api/collect/tasks/{task_id}/complete?batch_index={batch_index}
```

**调用方**：边端 `edge_client.py`

---

### 5.4 查询任务状态

```
GET /api/collect/tasks/{task_id}/status
```

**响应**：任务完整状态（含 `started_at`, `completed_at`, `result_batch_index`, `error_message`）

**调用方**：`views/Monitor.vue` → `api/system.js::getTaskStatus()`

---

### 5.5 采集历史

```
GET /api/collect/history?device_id={device_id}&limit={limit}
```

**调用方**：前端采集任务历史页面

---

## 6. 数据查看与诊断 (data_view)

> Router Prefix: `/api/data`
> Tag: `振动数据查看`

### 6.1 设备与批次查询

#### 6.1.1 获取所有设备批次列表
```
GET /api/data/devices
```
**响应**：设备列表及其批次、诊断概要

#### 6.1.2 获取某设备批次
```
GET /api/data/{device_id}/batches?include_special={include_special}
```
**参数**：`include_special: bool = True`

#### 6.1.3 获取某通道原始时域数据
```
GET /api/data/{device_id}/{batch_index}/{channel}?detrend={detrend}
```
**参数**：`detrend: bool = False`

#### 6.1.4 删除某设备所有特殊批次
```
DELETE /api/data/{device_id}/special
```

#### 6.1.5 删除某批次
```
DELETE /api/data/{device_id}/{batch_index}
```

---

### 6.2 频谱分析

#### 6.2.1 FFT 频谱
```
GET /api/data/{device_id}/{batch_index}/{channel}/fft?max_freq={max_freq}&detrend={detrend}
```
| 参数 | 类型 | 默认值 | 约束 |
|------|------|--------|------|
| `max_freq` | `Optional[int]` | `5000` | — |
| `detrend` | `bool` | `False` | — |

#### 6.2.2 STFT 时频谱
```
GET /api/data/{device_id}/{batch_index}/{channel}/stft?max_freq={max_freq}&nperseg={nperseg}&noverlap={noverlap}&detrend={detrend}
```
| 参数 | 类型 | 默认值 | 约束 |
|------|------|--------|------|
| `max_freq` | `Optional[int]` | `5000` | — |
| `nperseg` | `int` | `512` | `ge=64, le=4096` |
| `noverlap` | `int` | `256` | `ge=0, le=4095` |

**注意**：该端点为 `async def`，核心计算放入线程池

#### 6.2.3 统计特征指标
```
GET /api/data/{device_id}/{batch_index}/{channel}/stats?window_size={window_size}&step={step}&detrend={detrend}
```
| 参数 | 类型 | 默认值 | 约束 |
|------|------|--------|------|
| `window_size` | `int` | `1024` | `ge=64, le=8192` |
| `step` | `Optional[int]` | `None` | `ge=1, le=4096` |

---

### 6.3 包络与阶次分析

#### 6.3.1 包络谱分析
```
GET /api/data/{device_id}/{batch_index}/{channel}/envelope?max_freq={max_freq}&detrend={detrend}&method={method}&denoise={denoise}
```
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_freq` | `Optional[int]` | `1000` | 最大包络频率 |
| `detrend` | `bool` | `False` | 去趋势 |
| `method` | `str` | `"envelope"` | 包络方法 |
| `denoise` | `str` | `"none"` | 去噪方法 |

**注意**：该端点为 `async def`

#### 6.3.2 阶次跟踪
```
GET /api/data/{device_id}/{batch_index}/{channel}/order?freq_min={freq_min}&freq_max={freq_max}&samples_per_rev={samples_per_rev}&max_order={max_order}&rot_freq={rot_freq}&detrend={detrend}
```
| 参数 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `freq_min` | `float` | `10.0` | `ge=1.0, le=500.0` | 转频搜索下限 |
| `freq_max` | `float` | `100.0` | `ge=1.0, le=500.0` | 转频搜索上限 |
| `samples_per_rev` | `int` | `1024` | `ge=64, le=4096` | 每转采样点数 |
| `max_order` | `int` | `50` | `ge=5, le=200` | 最大阶次 |
| `rot_freq` | `Optional[float]` | `None` | `ge=1.0, le=500.0` | 已知转频（可选） |
| `detrend` | `bool` | `False` | — | 去趋势 |

**注意**：该端点为 `async def`

#### 6.3.3 倒谱分析
```
GET /api/data/{device_id}/{batch_index}/{channel}/cepstrum?max_quefrency={max_quefrency}&detrend={detrend}
```
| 参数 | 类型 | 默认值 | 约束 |
|------|------|--------|------|
| `max_quefrency` | `float` | `500.0` | `ge=10.0, le=2000.0` |

**注意**：该端点为 `async def`

---

### 6.4 齿轮与综合诊断

#### 6.4.1 齿轮诊断分析
```
GET /api/data/{device_id}/{batch_index}/{channel}/gear?detrend={detrend}&method={method}&denoise={denoise}
```
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `method` | `str` | `"standard"` | 齿轮分析方法 |
| `denoise` | `str` | `"none"` | 去噪方法 |

**注意**：该端点为 `async def`

#### 6.4.2 综合故障诊断分析（统一入口）
```
GET /api/data/{device_id}/{batch_index}/{channel}/analyze?detrend={detrend}&strategy={strategy}&bearing_method={bearing_method}&gear_method={gear_method}&denoise={denoise}
```
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `strategy` | `str` | `"standard"` | 诊断策略 |
| `bearing_method` | `str` | `"envelope"` | 轴承分析方法 |
| `gear_method` | `str` | `"standard"` | 齿轮分析方法 |
| `denoise` | `str` | `"none"` | 去噪方法 |

**注意**：该端点为 `async def`

#### 6.4.3 全算法对比分析
```
GET /api/data/{device_id}/{batch_index}/{channel}/full-analysis?detrend={detrend}&denoise={denoise}
```

**注意**：该端点为 `async def`

---

### 6.5 研究方法元数据与独立分析

#### 6.5.1 获取分析方法元数据
```
GET /api/data/method-info
```
**响应**：15 种分析方法的分类、名称和详细说明

#### 6.5.2 独立运行单个/全部分析方法
```
GET /api/data/{device_id}/{batch_index}/{channel}/method-analysis?method={method}&denoise={denoise}&detrend={detrend}
```
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `method` | `str` | `"all"` | 方法标识或 `"all"` |

**注意**：该端点为 `async def`

#### 6.5.3 研究级多算法集成诊断
```
GET /api/data/{device_id}/{batch_index}/{channel}/research-analysis?detrend={detrend}&profile={profile}&denoise={denoise}&max_seconds={max_seconds}
```
| 参数 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `profile` | `str` | `"balanced"` | — | 诊断配置：balanced/exhaustive |
| `max_seconds` | `float` | `5.0` | `ge=1.0, le=10.0` | 信号截断秒数 |

**注意**：该端点为 `async def`

---

### 6.6 诊断结果操作

#### 6.6.1 查询通道诊断结果
```
GET /api/data/{device_id}/{batch_index}/{channel}/diagnosis?denoise_method={denoise_method}
```
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `denoise_method` | `Optional[str]` | `None` | 指定去噪方法查询缓存 |

**查询优先级**：
1. 精确匹配 `device + batch + channel + denoise_method`
2. 该通道最新结果（不限去噪方法）
3. 批次级诊断记录（兼容旧数据）

#### 6.6.2 更新批次诊断结果
```
PUT /api/data/{device_id}/{batch_index}/diagnosis
```
**请求体**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `order_analysis` | `Optional[dict]` | 阶次分析结果 |
| `rot_freq` | `Optional[float]` | 估计转频 |

#### 6.6.3 单批次重新诊断
```
POST /api/data/{device_id}/{batch_index}/reanalyze
```
**说明**：覆盖更新数据库中的 Diagnosis 记录，要求设备在线

#### 6.6.4 全部批次重新诊断
```
POST /api/data/{device_id}/reanalyze-all
```
**说明**：逐批次串行执行以避免 OOM，返回 `{total, updated, errors, results}`

---

### 6.7 CSV 导出

```
GET /api/data/{device_id}/{batch_index}/{channel}/export?detrend={detrend}
```

**响应**：`StreamingResponse`（`text/csv; charset=utf-8-sig`，带 `Content-Disposition` 附件头）

**调用方**：`views/DataView.vue` → `window.open()`

---

## 7. 告警管理

### 7.1 获取告警列表

```
GET /api/alarms/?page={page}&size={size}&level={level}&resolved={resolved}&device_id={device_id}
```

**查询参数**：

| 参数 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `page` | `int` | `1` | `ge=1` | 页码 |
| `size` | `int` | `10` | `ge=1, le=100` | 每页条数 |
| `level` | `Optional[str]` | `None` | — | 级别过滤 |
| `resolved` | `Optional[int]` | `None` | — | 是否已处理 |
| `device_id` | `Optional[str]` | `None` | — | 设备过滤 |

**响应**：`{ code, data: { items, total, page, size } }`

**调用方**：`views/Alarm.vue` → `api/alarm.js::getHistoryAlarmList()`

---

### 7.2 处理告警

```
POST /api/alarms/{alarm_id}/resolve
```

**调用方**：`views/Alarm.vue` → `api/alarm.js::updateAlarmStatus(alarmId)`

---

### 7.3 删除告警

```
DELETE /api/alarms/{alarm_id}
```

**调用方**：`views/Alarm.vue` → `api/alarm.js::deleteAlarm(alarmId)`

---

## 8. 系统日志

### 8.1 获取日志

```
GET /api/logs/?lines={lines}
```

**查询参数**：`lines: int = 200`

**说明**：优先返回内存环形缓冲区日志；Linux 环境下追加 `journalctl -u CNN` 输出

**调用方**：`views/Logs.vue` → `api/system.js::getSystemLogs()`

---

## 9. 边端数据接入

### 9.1 数据上传

```
POST /api/ingest/
```

**请求体** (`dict`)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `device_id` | `string` | 设备编号 |
| `channels` | `List[dict]` | 通道数据列表（`{channel, data, sample_rate}`） |
| `compressed_data` | `Optional[str]` | Base64编码的压缩数据（替代 `channels`） |
| `batch_index` | `Optional[int]` | 指定批次号 |
| `is_special` | `Optional[int]` | 是否特殊采集 |

**内部辅助函数**：
- `_decompress_channels(payload)`：支持 `compressed_data`（base64+zlib+msgpack/json）和原图模式
- `_get_next_batch_index(db, device_id, is_special)`：普通数据 1~16 循环覆盖，特殊数据从 101 起自增永不覆盖

**调用方**：边端 `edge_client.py`

---

## 10. WebSocket 实时推送

### 10.1 监测数据推送

```
WS /ws/monitor?token={token}
```

**连接流程**：
1. 前端连接 WebSocket，携带 `token` 查询参数
2. 后端校验 `token`，通过后 `manager.connect(websocket)`
3. 心跳机制：前端发送 `{"type":"ping"}`，后端回复 `{"type":"pong"}`

**推送事件类型**：

| 事件类型 | 来源 | 说明 |
|---------|------|------|
| `sensor_update` | `ingest.py` | 新传感器数据到达 |
| `diagnosis_update` | `lifespan.py` | 诊断完成更新 |
| `alarm_new` | `alarms/__init__.py` | 新告警生成 |
| `device_online` | `offline_monitor.py` | 设备上线 |
| `device_offline` | `offline_monitor.py` | 设备离线 |

**前端订阅**：`views/Dashboard.vue`, `views/Monitor.vue`

---

## 附录 A：API 端点总表

### A.1 认证与系统

| 方法 | 路径 | 函数名 | 文件 | async |
|------|------|--------|------|-------|
| `POST` | `/api/auth/login` | `login` | `auth.py` | — |
| `GET` | `/api/dashboard/` | `get_dashboard` | `dashboard.py` | — |
| `GET` | `/api/logs/` | `get_logs` | `system.py` | — |

### A.2 设备管理

| 方法 | 路径 | 函数名 | 文件 | async |
|------|------|--------|------|-------|
| `GET` | `/api/devices/` | `get_devices` | `devices/core.py` | — |
| `GET` | `/api/devices/edge/config` | `get_edge_config` | `devices/config.py` | — |
| `GET` | `/api/devices/{id}/config` | `get_device_config` | `devices/config.py` | — |
| `PUT` | `/api/devices/{id}/config` | `update_device_config` | `devices/config.py` | — |
| `PUT` | `/api/devices/batch-config` | `update_batch_config` | `devices/config.py` | — |
| `GET` | `/api/devices/{id}/alarm-thresholds` | `get_alarm_thresholds` | `devices/config.py` | — |
| `PUT` | `/api/devices/{id}/alarm-thresholds` | `update_alarm_thresholds` | `devices/config.py` | — |

### A.3 监测与采集

| 方法 | 路径 | 函数名 | 文件 | async |
|------|------|--------|------|-------|
| `GET` | `/api/monitor/latest` | `get_latest_monitor` | `monitor.py` | — |
| `GET` | `/api/monitor/history` | `get_monitor_history` | `monitor.py` | — |
| `POST` | `/api/collect/request` | `request_collection` | `collect.py` | — |
| `GET` | `/api/collect/tasks` | `get_pending_tasks` | `collect.py` | — |
| `POST` | `/api/collect/tasks/{id}/complete` | `complete_task` | `collect.py` | — |
| `GET` | `/api/collect/tasks/{id}/status` | `get_task_status` | `collect.py` | — |
| `GET` | `/api/collect/history` | `get_collection_history` | `collect.py` | — |

### A.4 数据查看 (data_view)

| 方法 | 路径 | 函数名 | 文件 | async |
|------|------|--------|------|-------|
| `GET` | `/api/data/devices` | `get_all_device_data` | `data_view/core.py` | — |
| `GET` | `/api/data/{id}/batches` | `get_device_batches` | `data_view/core.py` | — |
| `GET` | `/api/data/{id}/{batch}/{ch}` | `get_channel_data` | `data_view/core.py` | — |
| `DELETE` | `/api/data/{id}/special` | `delete_special_batches` | `data_view/core.py` | — |
| `DELETE` | `/api/data/{id}/{batch}` | `delete_batch` | `data_view/core.py` | — |
| `GET` | `/api/data/{id}/{batch}/{ch}/fft` | `get_channel_fft` | `data_view/spectrum.py` | — |
| `GET` | `/api/data/{id}/{batch}/{ch}/stft` | `get_channel_stft` | `data_view/spectrum.py` | ✅ |
| `GET` | `/api/data/{id}/{batch}/{ch}/stats` | `get_channel_stats` | `data_view/spectrum.py` | — |
| `GET` | `/api/data/{id}/{batch}/{ch}/envelope` | `get_channel_envelope` | `data_view/envelope.py` | ✅ |
| `GET` | `/api/data/{id}/{batch}/{ch}/order` | `get_channel_order` | `data_view/order.py` | ✅ |
| `GET` | `/api/data/{id}/{batch}/{ch}/cepstrum` | `get_channel_cepstrum` | `data_view/cepstrum.py` | ✅ |
| `GET` | `/api/data/{id}/{batch}/{ch}/gear` | `get_channel_gear` | `data_view/gear.py` | ✅ |
| `GET` | `/api/data/{id}/{batch}/{ch}/analyze` | `get_channel_analyze` | `data_view/gear.py` | ✅ |
| `GET` | `/api/data/{id}/{batch}/{ch}/full-analysis` | `get_channel_full_analysis` | `data_view/gear.py` | ✅ |
| `GET` | `/api/data/method-info` | `get_method_info` | `data_view/research.py` | ✅ |
| `GET` | `/api/data/{id}/{batch}/{ch}/method-analysis` | `get_channel_method_analysis` | `data_view/research.py` | ✅ |
| `GET` | `/api/data/{id}/{batch}/{ch}/research-analysis` | `get_channel_research_analysis` | `data_view/research.py` | ✅ |
| `GET` | `/api/data/{id}/{batch}/{ch}/export` | `export_channel_csv` | `data_view/export.py` | — |
| `PUT` | `/api/data/{id}/{batch}/diagnosis` | `update_batch_diagnosis` | `data_view/diagnosis_ops.py` | ✅ |
| `GET` | `/api/data/{id}/{batch}/{ch}/diagnosis` | `get_channel_diagnosis` | `data_view/diagnosis_ops.py` | — |
| `POST` | `/api/data/{id}/{batch}/reanalyze` | `reanalyze_batch` | `data_view/diagnosis_ops.py` | ✅ |
| `POST` | `/api/data/{id}/reanalyze-all` | `reanalyze_all_batches` | `data_view/diagnosis_ops.py` | ✅ |

### A.5 告警

| 方法 | 路径 | 函数名 | 文件 | async |
|------|------|--------|------|-------|
| `GET` | `/api/alarms/` | `get_alarms` | `alarms.py` | — |
| `POST` | `/api/alarms/{id}/resolve` | `resolve_alarm` | `alarms.py` | — |
| `DELETE` | `/api/alarms/{id}` | `delete_alarm` | `alarms.py` | — |

### A.6 边端接入

| 方法 | 路径 | 函数名 | 文件 | async |
|------|------|--------|------|-------|
| `POST` | `/api/ingest/` | `ingest_data` | `ingest.py` | — |

### A.7 WebSocket

| 路径 | 函数名 | 文件 |
|------|--------|------|
| `/ws/monitor?token={token}` | `websocket_endpoint` | `main.py` |
