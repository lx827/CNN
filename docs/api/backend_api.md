# 后端 API 接口文档

> **文档用途**：完整记录云端 FastAPI 后端的所有 REST API 端点、WebSocket 接口、请求/响应参数及调用约束。
> **维护要求**：新增、修改或删除任何 API 端点时，必须同步更新本文档、`frontend_backend_interaction.md` 与机器可读 `openapi.json`。算法数学语义不在本文复制，统一链接 `docs/algorithms/`。

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
11. [OpenAPI 契约与端点使用清点](#11-openapi-契约与端点使用清点)

---

## 通用约定

### 基础 URL

- 开发环境：`http://localhost:8000`
- 生产环境：`http://8.137.96.104:8000`

### 响应格式

2026-10-21：经过 DataView 公共转换器的算法结果，NumPy 类型递归转为 JSON 原生类型，NaN/Infinity 使用 `null` 表示缺失值，避免严格 JSON 编码失败。

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

### OpenAPI 契约（唯一事实源）

机器可读契约入库于 [`docs/api/openapi.json`](./openapi.json)，由 FastAPI 自动生成。**修改任何后端路由后**，在仓库根执行以下命令刷新并随代码提交：

```bash
uv run python scripts/export_openapi.py
```

> 新鲜度机制（issue #49 决策）：采用手动导出命令，不做 CI 校验——本项目无 CI 流水线，端点变更频率低，文档评审时核对 openapi.json diff 即可。

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

**调用方**：`views/Login.vue` → `api/auth.js::login()`

认证依赖同时兼容 JWT Bearer 与边端 API Key，具体适用端点见下文。令牌生成、校验和认证依赖的函数签名以 `cloud/app/api/auth.py` 源码 docstring 为准，不在 API 文档复制内部函数接口。

---

## 2. Dashboard 总览

2026-10-21：设备最新诊断摘要改由数据库统一筛选（`analyzed_at` 降序、同时间 `id` 降序），不加载完整算法大字段。告警四项统计合并为一次条件聚合；有设备时总览共三次 SELECT，响应字段不变。

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

> **2026-05-19 修复**：`health_score` 不再因设备离线而返回 `None`。离线仅影响 `status` 标签（显示 "offline"），已存储的诊断数据正常返回。

**调用方**：`views/Dashboard.vue` → `api/dashboard.js::getDeviceInfo()`

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

**调用方**：`views/Settings.vue`, `views/Alarm.vue`, `views/Monitor.vue` → `api/devices.js::getDevices()`

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

**调用方**：`views/Settings.vue` → `api/devices.js::getDeviceConfig(deviceId)`

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

**调用方**：`views/Settings.vue` → `api/devices.js::updateDeviceConfig(deviceId, payload)`

---

### 3.4 批量更新设备配置

```
PUT /api/devices/batch-config
```

**请求体** (`dict`)：同上，应用到所有设备

**响应**：`{ updated_count, updated_fields }`

**调用方**：`views/Settings.vue` → `api/devices.js::updateBatchDeviceConfig(payload)`

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

**调用方**：边端（Rust `edge/`；旧 `edge_client.py` 已随 2026-11 布局重构退役）启动时拉取

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

**调用方**：`views/Settings.vue` → `api/devices.js::getAlarmThresholds(deviceId)`

---

### 3.7 更新告警阈值

```
PUT /api/devices/{device_id}/alarm-thresholds
```

**请求体** (`dict`)：阈值配置对象

**调用方**：`views/Settings.vue` → `api/devices.js::updateAlarmThresholds(deviceId, payload)`

---

## 4. 实时监测

2026-10-21：`/latest` 不再额外加载一条完整波形用于判断未使用的特殊标记，最新诊断只选取转频列；`/history` 通过批次 IN 查询消除 N+1。有数据时分别最多四次（特殊优先回退时五次）和两次 SELECT。保留既有批次选择与返回格式；`limit` 目前仍是兼容参数，不裁剪通道。

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

**响应**：每条含 `data`（时域）、`fft_freq`、`fft_amp`、`channel_name` 等。FFT 对最多 `FFT_POINTS` 个采样完整计算后再按 `FFT_MAX_FREQ` 截断显示；采用去均值、周期 Hann 和单边峰值幅值，频率单位 Hz、幅值单位与输入一致，DC/Nyquist 不翻倍。

**内部常量**：

- `TIME_DOMAIN_POINTS = 2560`（时域返回点数）
- `FFT_POINTS = 25600`（FFT用1秒数据）
- `FFT_MAX_FREQ = 5000`（FFT最高返回频率）

**调用方**：`views/Monitor.vue` → `api/monitor.js::getRealtimeVibrationData()`

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

**调用方**：边端（Rust `edge/`；旧 `edge_client.py` 已退役）

---

### 5.3 标记任务完成

```
POST /api/collect/tasks/{task_id}/complete?batch_index={batch_index}
```

**调用方**：边端（Rust `edge/`；旧 `edge_client.py` 已退役）

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

### 5.6 DC24 实时采集边端

`POST /api/acquisition/agents/heartbeat` 的 `state.transport` 可选，真实边端上报 `jmserver` 或 `python_tcp`。`GET /api/acquisition/agents` 返回该字段供本机启动器识别连接方式。没有该字段的旧真实边端按 `python_tcp` 处理。两种方式的采集来源均为 `dc24_tcp`，已保存记录在 `metadata.transport` 中标记本次连接方式。操作见 [DC24 现场采集](../DC24_ACQUISITION.md)。

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
GET /api/data/{device_id}/{batch_index}/{channel}?detrend={detrend}&denoise={denoise}
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `detrend` | `bool` | `False` | 线性去趋势 |
| `denoise` | `str` | `"none"` | 预处理方法 |

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

三个端点均在业务层先截取最多 5 秒，再去趋势/去噪并复用现有线程池计算。完整数值表示先于展示截断生成；数学定义见 [基础数值表示契约](../algorithms/numeric/INDEX.md)。

#### 6.2.1 FFT 频谱

```
GET /api/data/{device_id}/{batch_index}/{channel}/fft?max_freq={max_freq}&detrend={detrend}&denoise={denoise}
```

| 参数 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `max_freq` | `Optional[int]` | `5000` | — | 最大频率 |
| `detrend` | `bool` | `False` | — | 线性去趋势 |
| `denoise` | `str` | `"none"` | — | 预处理方法 |

**响应 data**：`{device_id, batch_index, channel, channel_name, sample_rate, is_special, fft_freq, fft_amp}`。`fft_freq` 为 Hz，保留两位小数；`fft_amp` 为去均值、周期 Hann 相干增益补偿后的单边峰值幅值，保留四位小数，单位与输入一致。DC/Nyquist 不翻倍；`max_freq` 只截断显示，传空值时不截断。

#### 6.2.2 STFT 时频谱

```
GET /api/data/{device_id}/{batch_index}/{channel}/stft?max_freq={max_freq}&nperseg={nperseg}&noverlap={noverlap}&detrend={detrend}&denoise={denoise}
```

| 参数 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `max_freq` | `Optional[int]` | `5000` | — | 最大频率 |
| `nperseg` | `int` | `512` | `ge=64, le=4096` | 窗口长度 |
| `noverlap` | `int` | `256` | `ge=0, le=4095` | 重叠长度 |
| `detrend` | `bool` | `False` | — | 线性去趋势 |
| `denoise` | `str` | `"none"` | — | 预处理方法 |

**注意**：该端点为 `async def`，核心计算放入线程池。实际窗口随短记录缩小，重叠不超过实际窗口减 1，FFT 长度至少覆盖实际窗口。

**响应 data**：`{device_id, batch_index, channel, channel_name, sample_rate, is_special, time, freq, magnitude}`。`time` 为秒、`freq` 为 Hz；`magnitude` 形状为 `(frequency, time)`，由单边峰值幅值计算 `20*log10(amplitude+1e-10)` dB。两端补零使首帧时间通常为 0；`max_freq` 只截断显示。

#### 6.2.3 统计特征指标

```
GET /api/data/{device_id}/{batch_index}/{channel}/stats?window_size={window_size}&step={step}&detrend={detrend}&denoise={denoise}
```

| 参数 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `window_size` | `int` | `1024` | `ge=64, le=8192` | 窗口大小 |
| `step` | `Optional[int]` | `None` | `ge=1, le=4096` | 滑动步长 |
| `detrend` | `bool` | `False` | — | 线性去趋势 |
| `denoise` | `str` | `"none"` | — | 预处理方法 |

**响应 data**：包含 `peak/rms/kurtosis/skewness/margin/shape_factor/impulse_factor/crest_factor`、`windowed_kurtosis`、`window_series` 和 `window_params`，以及设备/批次/通道元数据。总体指标使用 5 秒限制内的完整信号；窗口序列只使用周期 Hann 完整窗口，`window_params` 返回实际窗口和步长。绘图抽点不参与统计。

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

高级轴承补充参数：`rot_freq_hz` 为可选正值恒转频 Hz；`target_fault` 为 BPFO/BPFI/BSF/FTF，`target_frequency_hz` 或 `period_samples` 给 MCKD 显式周期；`comb_frequencies_hz` 使用重复 query 参数传多个正频率，`comb_is_stable=true` 表示调用方确认整段梳状干扰稳定。完整约束以 OpenAPI 为准。

**注意**：该端点为 `async def`。`max_freq` 只截断展示频谱，不改变完整分析范围或诊断结果。

**响应 data（新契约）**：

- `spectrum`：`{frequency_hz, amplitude, amplitude_unit, scaling}`；标准包络为 `single_sided_amplitude`。
- `band`：`{low_hz, high_hz, center_hz, width_hz}`，为实际滤波频带。
- `features`：`spectral_power_proxy`（幅值平方和）、`spectral_power_unit`、故障频率及谐波能量比。
- `evaluation`：`{status, indicators}`；单项 `not_evaluable` 带 `reason`、`significant=None`，不表示未检出或健康。
- 另含 `method/strategy/rot_freq_hz/envelope_low_pass_hz` 和方法元数据；不再返回 `envelope_freq`、`envelope_amp` 或顶层 `fault_indicators`。

当前高级方法标识为 `filter_bank_sk/spectral_kurtosis/cpw/med/mckd/teager/sc_scoh`，不接受旧 `kurtogram` 冒名。`analysis_status/reason` 说明计算/前提状态，与 `evaluation.status` 分开；无稳定梳状先验的 CPW 不生成谱，MCKD 缺显式目标实际执行 MED 并保存 `requested_method/fallback_reason`。SC/SCoh 使用 `evaluation_kind=sc_scoh` 和规范 `evaluation.indicators`，二维 `cyclic_spectrum` 含循环/载波 Hz、SC 幅值（输入单位平方/Hz）、无量纲 SCoh 和循环分辨率；可以没有普通 `spectrum`。TEO 最终包络谱单位为 `input_signal^2`。

#### 6.3.2 阶次跟踪

```
GET /api/data/{device_id}/{batch_index}/{channel}/order?freq_min={freq_min}&freq_max={freq_max}&samples_per_rev={samples_per_rev}&max_order={max_order}&rot_freq={rot_freq}&detrend={detrend}&denoise={denoise}
```

| 参数 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `freq_min` | `float` | `10.0` | `ge=1.0, le=500.0` | 转频搜索下限 |
| `freq_max` | `float` | `100.0` | `ge=1.0, le=500.0` | 转频搜索上限 |
| `samples_per_rev` | `int` | `1024` | `ge=64, le=4096` | 每转采样点数 |
| `max_order` | `int` | `50` | `ge=5, le=200` | 最大阶次 |
| `rot_freq` | `Optional[float]` | `None` | `ge=1.0, le=500.0` | 已知转频（可选） |
| `detrend` | `bool` | `False` | — | 去趋势 |
| `denoise` | `str` | `"none"` | — | 预处理方法 |

**注意**：该端点为 `async def`

**响应与算法契约（2026-11-08）**：响应字段不变。`orders` 为 FFT bin 阶次轴，`spectrum` 为输入单位下的 `single_sided_amplitude`，两者保留六位小数；不再使用窗能量归一化幅值。已知 `rot_freq` 走恒速等角采样；自动模式按局部转频 CV 区分逐帧谱平均与 STFT 连续相位重采样，单帧或 slow 失败也会尝试 fast。快速变速无可靠脊线、持续触及搜索边界或标量估计不可判定时返回 HTTP 400，不默认 10 Hz、不返回伪正常谱。转速估计使用未去噪信号，`denoise` 只影响重采样输入。仅更新已有 `channel=0/denoise_method="none"` 批次记录（兼容两列均 NULL 的旧记录）；无记录时不创建健康诊断，通道缓存不被覆盖。

#### 6.3.3 倒谱分析

```
GET /api/data/{device_id}/{batch_index}/{channel}/cepstrum?max_quefrency={max_quefrency}&detrend={detrend}&denoise={denoise}
```

| 参数 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `max_quefrency` | `float` | `500.0` | `ge=10.0, le=2000.0` | 最大倒频率 |
| `detrend` | `bool` | `False` | — | 线性去趋势 |
| `denoise` | `str` | `"none"` | — | 预处理方法 |

**注意**：该端点为 `async def`。倒谱算法内部倒频率单位为秒，HTTP 查询与响应使用毫秒。

**响应 data**：`{device_id, batch_index, channel, channel_name, sample_rate, is_special, max_quefrency, quefrency, cepstrum, peaks}`。`quefrency` 为非负倒频率轴（ms），`cepstrum` 为周期 Hann、去均值 log 幅值谱的实 IFFT，不是 log-power 倒谱。`peaks` 含 `{quefrency_ms, freq_hz, amplitude}`；`freq_hz=1/quefrency_s` 表示谱线间隔，显示峰不构成机械故障阈值。

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

**响应**：当前源码所开放方法的分类、名称、前提与状态；前端据此动态渲染，不固定方法总数。未迁移的复合研究流程不得显示为已接入融合。

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

1. 精确匹配 `device + batch + channel + denoise_method` → 返回 `engine_result` 或 `full_analysis`
2. 若以上两列为空 → 回退到 `order_analysis.channels[ch{N}]` 提取该通道完整诊断结果
3. 该通道最新结果（不限去噪方法）→ 同上两步
4. 批次级诊断记录 → 优先 `order_analysis.channels` → `order_analysis.engine_result` → 传统批次数据（兼容旧数据）

**响应体 `data` 字段说明**（通道级 `full_analysis` 完整结构）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `health_score` | `int/null` | 有证据时健康度 0-100；不可判定允许空值 |
| `status` | `str` | normal/warning/critical；缺可评估证据可为 indeterminate，不能映射正常 |
| `fault_likelihood` | `float` | 故障似然度 |
| `fault_label` | `str` | 故障标签 |
| `rot_freq_hz` | `float` | 估计转频 |
| `time_features` | `dict` | 时域特征（rms/kurtosis/crest_factor/cusum/ewma 等） |
| `bearing` | `dict` | 最佳轴承诊断结果（含 fault_indicators） |
| `gear` | `dict` | 最佳齿轮诊断结果（含 fault_indicators） |
| `ensemble` | `dict` | **集成诊断结果**（见下表） |
| `recommendation` | `str` | 维护建议 |

**`ensemble` 子字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `profile` | `str` | runtime/balanced/exhaustive |
| `bearing_votes` | `dict` | 各轴承算法投票详情（method→{confidence, param_hits, stat_hits, hits}） |
| `gear_votes` | `dict` | 各齿轮算法投票详情（method→{confidence, critical_hits, warning_hits, hits}） |
| `bearing_vote_fraction` | `float` | 轴承投票一致率 |
| `gear_vote_fraction` | `float` | 齿轮投票一致率 |
| `bearing_confidence` | `float` | 轴承综合置信度 |
| `gear_confidence` | `float` | 齿轮综合置信度 |
| `time_confidence` | `float` | 时域冲击置信度 |
| `best_bearing` | `str` | 最佳轴承算法键名 |
| `best_gear` | `str` | 最佳齿轮算法键名 |
| `ds_fusion` | `dict` | D-S 证据融合结果（fused_bpa/belief/plausibility/conflict/dominant_fault） |

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
GET /api/data/{device_id}/{batch_index}/{channel}/export?detrend={detrend}&denoise={denoise}
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

**调用方**：`views/Alarm.vue` → `api/alarms.js::getHistoryAlarmList()`

---

### 7.2 处理告警

```
POST /api/alarms/{alarm_id}/resolve
```

**调用方**：`views/Alarm.vue` → `api/alarms.js::updateAlarmStatus(alarmId)`

---

### 7.3 删除告警

```
DELETE /api/alarms/{alarm_id}
```

**调用方**：`views/Alarm.vue` → `api/alarms.js::deleteAlarm(alarmId)`

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

**调用方**：边端（Rust `edge/`；旧 `edge_client.py` 已退役）

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

### 10.2 DC24 实时示波窗口推送（2026-11 新增，issue #51）

```
WS /ws/acquisition/sessions/{session_id}/view?token={token}
```

网页读取实时窗口的主通道：边端 `POST /sessions/{id}/frames` 上报保持 HTTP 不变；原 REST `GET /sessions/{id}/view` 轮询保留作兼容与回退，两者共用 `build_view_payload()` 同一套窗口计算。

**连接**：`token` 查询参数经 `verify_token_string` 校验（浏览器 WS 无法携带 Authorization 头）；无效令牌以 `WS_1008` 拒绝；会话不存在（后端可能已重启）接受握手后以 `4404` 关闭，前端走既有 REST 恢复路径（`GET /agents/{agent_id}/session`）。

**连接查询参数**（与 REST view 一致的初始选项）：`waveform/fft/rms/envelope/band_low/band_high/wave_seconds`。

**客户端消息**：

| 消息 | 说明 |
|------|------|
| `{"type":"ping"}` | 心跳，服务端回 `{"type":"pong"}` |
| `{"type":"options", fft?, rms?, envelope?, band_low?, band_high?, wave_seconds?}` | 更新分析选项；包络频带校验与 REST 一致（`0 < 下限 < 上限 < 采样率/2`），非法频带回 `{"type":"error","data":{"detail":...}}` 且不改选项 |

**服务端推送**（限频 0.4s，与原 500ms 轮询同节奏；计算走共享两线程池）：

| 消息 | 触发 | data |
|------|------|------|
| `{"type":"session","data":{...}}` | 会话快照变化（状态/录制进度/错误） | `live.snapshot()` |
| `{"type":"view","data":{...}}` | 连接即推 + `revision` 变化（新帧）或选项变化 | 与 REST view 的 `data` 完全同构（含 `waiting` 短数据分支、`fresh` 标记） |

**前端订阅**：`views/Acquisition.vue`（`utils/websocket.js::createWebSocketClient`，WS 未连上时回退 REST 轮询，断线自动重连）

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
| `/ws/acquisition/sessions/{id}/view?token={token}` | `ws_view` | `acquisition_live.py` |

---

## 11. OpenAPI 契约与端点使用清点

> 2026-11-08（issue #49）：以 `docs/api/openapi.json` 为准，对照前端 `src/api/` 按域模块清点端点使用情况。**只记录，不删除任何后端端点。**

### 11.1 总量

| 分类 | 数量 |
|------|------|
| OpenAPI 路径总数 | 69 |
| 前端 `src/api/` 已封装 | 54 |
| 前端未封装（边端/系统专用） | 15 |

### 11.2 前端未封装的端点（15 个）

以下端点无任何前端 `src/api/` 模块引用，调用方为 Rust 边端（`edge/`）、已退役的旧边端脚本或运维场景，**保留不动**：

| 方法 | 路径 | 实际调用方 |
|------|------|-----------|
| `GET` | `/` | 浏览器/运维手动访问的服务信息页 |
| `POST` | `/api/ingest/` | 边端数据上报（Rust `edge/`） |
| `GET` | `/api/devices/edge/config` | 边端拉取采集配置（Rust `edge/`） |
| `GET` | `/api/collect/tasks` | 待领采集任务列表（边端轮询） |
| `POST` | `/api/collect/tasks/{task_id}/complete` | 边端完成任务回报 |
| `POST` | `/api/acquisition/agents/heartbeat` | DC24 边端心跳 |
| `GET` | `/api/acquisition/agents/{agent_id}/next` | DC24 边端领取任务 |
| `GET` | `/api/acquisition/agents/{agent_id}/control` | DC24 边端控制轮询（`edge_only`） |
| `POST` | `/api/acquisition/agents/{agent_id}/directory-result` | DC24 边端回传目录选择结果（`edge_only`） |
| `POST` | `/api/acquisition/jobs/{job_id}/progress` | DC24 边端任务进度上报 |
| `POST` | `/api/acquisition/jobs/{job_id}/upload` | DC24 边端整包上传 |
| `PUT` | `/api/acquisition/jobs/{job_id}/stream-files/{name}` | DC24 边端流式上传（`edge_only`） |
| `POST` | `/api/acquisition/jobs/{job_id}/finish-stream` | DC24 边端完成流式上传（`edge_only`） |
| `POST` | `/api/acquisition/sessions/{session_id}/frames` | DC24 边端示波帧上报（`edge_only`，HTTP 保持不变） |
| `POST` | `/api/acquisition/sessions/{session_id}/state` | DC24 边端会话状态上报（`edge_only`） |

### 11.3 已封装但当前无视图调用的函数（预留）

以下前端 api 模块函数无任何视图消费，属预留能力，端点本身有其他价值（调试、后续功能），保留：

| 函数 | 模块 | 端点 |
|------|------|------|
| `getMonitorHistory` | `api/monitor.js` | `GET /api/monitor/history` |
| `getDeviceBatches` | `api/data.js` | `GET /api/data/{device_id}/batches` |
| `getCollectionHistory` | `api/system.js` | `GET /api/collect/history` |
| `createAcquisition` / `getAcquisition` / `stopAcquisition` / `getAcquisitionAnalysis` / `getAcquisitionWaveform` | `api/acquisition.js` | `POST/GET /api/acquisition/jobs*`（回放任务族） |
