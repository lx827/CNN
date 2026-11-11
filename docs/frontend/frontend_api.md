# 前端接口文档

> **文档用途**：汇总 `wind-turbine-diagnosis` 前端项目中的所有 API 封装、Vue 页面组件及通用组件的接口定义，便于前后端联调与后续维护。  
> **维护提醒**：每当新增/修改 API 或组件 Props/Emits 时，请同步更新本文档。文档应与代码保持一致，避免口头约定。

---

## 目录

1. [Axios 基础配置](#1-axios-基础配置)
2. [API 层](#2-api-层)
   - 2.1 [api/index.js — 按域模块汇总出口](#21-apiindexjs--按域模块汇总出口)
   - 2.2 [api/auth.js — 认证](#22-apiauthjs--认证)
   - 2.3 [api/dashboard.js — 设备总览](#23-apidashboardjs--设备总览)
   - 2.4 [api/monitor.js — 实时监测](#24-apimonitorjs--实时监测)
   - 2.5 [api/data.js — 数据查看](#25-apidatajs--数据查看)
   - 2.6 [api/diagnosis.js — 诊断](#26-apidagnosisjs--诊断)
   - 2.7 [api/devices.js — 设备配置](#27-apidevicesjs--设备配置)
   - 2.8 [api/alarms.js — 告警管理](#28-apialarmsjs--告警管理)
   - 2.9 [api/system.js — 系统与采集](#29-apisystemjs--系统与采集)
   - 2.10 [api/acquisition.js — DC24 采集与实时示波](#210-apiacquisitionjs--dc24-采集与实时示波)
   - 2.11 [api/ingest.js — 边端数据接入（预留）](#211-apiingestjs--边端数据接入预留)
3. [Views 页面组件](#3-views-页面组件)
   - 3.1 [Dashboard.vue](#31-dashboardvue)
   - 3.2 [DataView.vue](#32-dataviewvue)
   - 3.3 [Monitor.vue](#33-monitorvue)
   - 3.4 [ResearchDiagnosis.vue](#34-researchdiagnosisvue)
   - 3.5 [Alarm.vue](#35-alarmvue)
   - 3.6 [Settings.vue](#36-settingsvue)
   - 3.7 [Login.vue](#37-loginvue)
   - 3.8 [Logs.vue](#38-logsvue)
4. [Components 通用组件](#4-components-通用组件)
   - 4.1 [Layout.vue](#41-layoutvue)
   - 4.2 [VibrationChart.vue](#42-vibrationchartvue)
   - 4.3 [DiagnosisDetail.vue](#43-diagnosisdetailvue)
   - 4.4 [DetailHeader.vue](#44-detailheadervue)
   - 4.5 [DeviceTable.vue](#45-devicetablevue)
5. [WebSocket 事件汇总](#5-websocket-事件汇总)
6. [Composables 组合式函数（2026-11 拆分）](#6-composables-组合式函数2026-11-拆分)

---

## 1. Axios 基础配置

**文件路径**：`src/utils/request.js`

| 配置项 | 说明 |
|--------|------|
| `baseURL` | 动态获取当前 host（开发环境通过 Vite 代理转发到后端） |
| 请求拦截器 | 从 `localStorage` 读取 `token`，自动注入 `Authorization: Bearer {token}` |
| 响应拦截器 | 若响应体中 `code !== 200`，抛出错误提示；若返回 `401`，跳转登录页 |

```javascript
// 典型调用方式
import request from '@/utils/request';

request.get('/api/dashboard/').then(res => { ... });
```

---

## 2. API 层

> 所有 API 函数均位于 `src/api/` 目录下，统一通过 `request` 实例发起 HTTP 请求。参数中的 `deviceId`、`batchIndex`、`channel` 等在后端路径中以模板变量形式填充。
>
> **2026-11-08（issue #49）重组**：api 层按后端路由域拆分为独立模块，`api/index.js` 仅作汇总出口（re-export）。视图优先从具体域模块导入（如 `import { getChannelFFT } from '../api/data'`），跨域批量导入可用 `from '../api'`。旧 `api/device.js`、`api/alarm.js` 已分别更名为 `api/devices.js`、`api/alarms.js`。

### 2.1 api/index.js — 按域模块汇总出口

**文件路径**：`src/api/index.js`

汇总 re-export 以下全部域模块，不定义任何函数：`auth` / `dashboard` / `monitor` / `data` / `diagnosis` / `devices` / `alarms` / `system` / `acquisition` / `ingest`。

### 2.2 api/auth.js — 认证

**文件路径**：`src/api/auth.js`

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `login(password)` | `password: string` | `{ token: string }` | `POST /api/auth/login` | `Login.vue` |

### 2.3 api/dashboard.js — 设备总览

**文件路径**：`src/api/dashboard.js`

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `getDeviceInfo()` | 无 | 设备总览数据对象 | `GET /api/dashboard/` | `Dashboard.vue`, `stores/deviceStore.js` |

> **2026-05-19 修复**：离线设备的 `health` 和 `components[].health` 不再设为 `null`，始终从诊断数据计算。离线仅标记 `status: 'offline'`。

### 2.4 api/monitor.js — 实时监测

**文件路径**：`src/api/monitor.js`

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `getRealtimeVibrationData(device_id, prefer_special)` | `device_id: string`<br>`prefer_special?: boolean`（默认 `false`） | 实时振动数据数组 | `GET /api/monitor/latest?device_id=...&prefer_special=...` | `Monitor.vue` |
| `getMonitorHistory(device_id, channel, batches, include_special)` | `device_id: string`<br>`channel?: number`（默认 `1`）<br>`batches?: number`（默认 `16`）<br>`include_special?: boolean`（默认 `true`） | `{ device_id, channel, items: [{batch_index, ...}] }` | `GET /api/monitor/history?device_id=...&channel=...&batches=...&include_special=...` | 预留（当前无视图调用） |

```javascript
// 使用示例
import { getRealtimeVibrationData } from '@/api/monitor';

const data = await getRealtimeVibrationData('WTG-001', true);
```

### 2.5 api/data.js — 数据查看

**文件路径**：`src/api/data.js`

设备/批次列表、原始波形、各频谱计算、数据删除与 CSV 导出。

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `getAllDeviceData()` | 无 | 所有设备及批次数据 | `GET /api/data/devices` | `DataView.vue`, `ResearchDiagnosis.vue` |
| `getDeviceBatches(deviceId)` | `deviceId: string` | 批次列表 | `GET /api/data/{deviceId}/batches` | 预留（当前无视图调用） |
| `getChannelData(deviceId, batchIndex, channel, detrend, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`detrend?: bool`<br>`denoise?: string` | 时域数据点数组 | `GET /api/data/{deviceId}/{batchIndex}/{channel}` | `DataView.vue` |
| `getChannelFFT(deviceId, batchIndex, channel, max_freq, detrend, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`max_freq?: number`<br>`detrend?: bool`<br>`denoise?: string` | FFT 频谱数据 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/fft?...` | `DataView.vue` |
| `getChannelSTFT(deviceId, batchIndex, channel, max_freq, nperseg, noverlap, detrend, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`max_freq?: number`<br>`nperseg?: number`<br>`noverlap?: number`<br>`detrend?: bool`<br>`denoise?: string` | STFT 时频图数据 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/stft?...` | `DataView.vue` |
| `getChannelEnvelope(deviceId, batchIndex, channel, max_freq, detrend, method, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`max_freq?: number`<br>`detrend?: bool`<br>`method?: string`<br>`denoise?: string` | 结构化轴承包络分析结果 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/envelope?...` | `DataView.vue` |
| `getChannelGear(deviceId, batchIndex, channel, method, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`method?: string`<br>`denoise?: string` | 齿轮诊断指标 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/gear?...` | `DataView.vue` |
| `getChannelOrder(deviceId, batchIndex, channel, freq_min, freq_max, samples_per_rev, max_order, rot_freq, detrend, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`freq_min?: number`<br>`freq_max?: number`<br>`samples_per_rev?: number`<br>`max_order?: number`<br>`rot_freq?: number`<br>`detrend?: bool`<br>`denoise?: string` | 阶次谱数据 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/order?...` | `DataView.vue` |
| `getChannelCepstrum(deviceId, batchIndex, channel, max_quefrency, detrend, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`max_quefrency?: number`<br>`detrend?: bool`<br>`denoise?: string` | 倒谱数据 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/cepstrum?...` | `DataView.vue` |
| `getChannelStats(deviceId, batchIndex, channel, window_size, step, detrend, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`window_size?: number`<br>`step?: number`<br>`detrend?: bool`<br>`denoise?: string` | 统计指标数据 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/stats?...` | `DataView.vue` |
| `deleteBatch(deviceId, batchIndex)` | `deviceId: string`<br>`batchIndex: number` | 删除结果 | `DELETE /api/data/{deviceId}/{batchIndex}` | `DataView.vue`, `DeviceTable.vue` |
| `deleteSpecialBatches(deviceId)` | `deviceId: string` | 删除结果 | `DELETE /api/data/{deviceId}/special` | `DataView.vue`, `DeviceTable.vue` |
| `exportChannelCSV(deviceId, batchIndex, channel, detrend, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`detrend?: bool`<br>`denoise?: string` | 无（`window.open` 触发下载） | `GET /api/data/{deviceId}/{batchIndex}/{channel}/export` | `DataView.vue` |

> **轴承响应契约（2026-11-11）**：`data.spectrum` 为 `{frequency_hz, amplitude, amplitude_unit, scaling}`，图表读取实际单位与缩放；TEO 的幅值单位为输入单位平方。`band` 是实际频带，`features` 为指标，`evaluation {status,indicators}` 是独立评估。`indeterminate/not_evaluable` 不渲染为正常。SC/SCoh 通过 `evaluation_kind=sc_scoh` 读取同一规范 `evaluation.indicators`，没有普通谱时不创建空图；专属二维谱读取 `cyclic_spectrum` 的循环/载波 Hz、SC 和 SCoh。前端不回读旧 `sc_scoh_indicators`、`envelope_freq/envelope_amp` 或轴承顶层 `fault_indicators`。齿轮按自己的规范评估与兼容字段展示。

高级方法选项使用 `filter_bank_sk` 的真实名称，不保留旧 `kurtogram`；CPW 需要重复 query 的 `comb_frequencies_hz` 与稳定性声明；MCKD 可传 `target_fault/target_frequency_hz/period_samples`。研究 API 封装通过 config 对象传递这些先验并使用重复 query 序列化，具体签名以源码为准。结果存在 `requested_method/fallback_reason` 时显示实际 MED 回退；`analysis_status/reason` 与评估状态分开显示。

### 2.6 api/diagnosis.js — 诊断

**文件路径**：`src/api/diagnosis.js`

诊断缓存读取、综合/全量/研究级分析、方法级分析、诊断更新与重新诊断。

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `getChannelDiagnosis(deviceId, batchIndex, channel, denoise_method)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`denoise_method?: string` | 诊断缓存结果 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/diagnosis?denoise_method=...` | `DataView.vue`, `DiagnosisDetail.vue` |
| `getChannelAnalyze(deviceId, batchIndex, channel, strategy, bearing_method, gear_method, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`strategy?: string`<br>`bearing_method?: string`<br>`gear_method?: string`<br>`denoise?: string` | 综合分析结果 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/analyze?...` | `DataView.vue` |
| `getChannelFullAnalysis(deviceId, batchIndex, channel, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`denoise?: string` | 全算法分析结果 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/full-analysis?denoise=...` | `DataView.vue` |
| `getChannelResearchAnalysis(deviceId, batchIndex, channel, profile, denoise, max_seconds)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`profile?: string`<br>`denoise?: string`<br>`max_seconds?: number` | 研究级分析结果 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/research-analysis?...` | `ResearchDiagnosis.vue` |
| `getMethodInfo()` | 无 | 可用分析方法列表 | `GET /api/data/method-info` | `ResearchDiagnosis.vue` |
| `getChannelMethodAnalysis(deviceId, batchIndex, channel, method, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`method: string`<br>`denoise?: string` | 单方法分析结果 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/method-analysis?method=...&denoise=...` | `ResearchDiagnosis.vue` |
| `updateBatchDiagnosis(deviceId, batchIndex, order_analysis, rot_freq)` | `deviceId: string`<br>`batchIndex: number`<br>`order_analysis: object`<br>`rot_freq?: number` | 更新结果 | `PUT /api/data/{deviceId}/{batchIndex}/diagnosis` | `DataView.vue` |
| `reanalyzeBatch(deviceId, batchIndex)` | `deviceId: string`<br>`batchIndex: number` | 重新诊断结果 | `POST /api/data/{deviceId}/{batchIndex}/reanalyze` | `DataView.vue` |
| `reanalyzeAllDevice(deviceId)` | `deviceId: string` | 批量重新诊断汇总 | `POST /api/data/{deviceId}/reanalyze-all` | `DataView.vue` |

```javascript
// 典型调用示例
import { getChannelFFT } from '@/api/data';
import { getChannelFullAnalysis, reanalyzeBatch } from '@/api/diagnosis';

const fft = await getChannelFFT('WTG-001', 1, 1, 5000);
const full = await getChannelFullAnalysis('WTG-001', 1, 1, { denoise: 'wavelet' });
await reanalyzeBatch('WTG-001', 1);
```

### 2.7 api/devices.js — 设备配置

**文件路径**：`src/api/devices.js`（原 `api/device.js`，2026-11 更名）

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `getDevices()` | 无 | 设备列表 | `GET /api/devices/` | `Settings.vue`, `Monitor.vue`, `Alarm.vue` |
| `getDeviceConfig(deviceId)` | `deviceId: string` | 设备配置对象 | `GET /api/devices/{deviceId}/config` | `Settings.vue` |
| `updateDeviceConfig(deviceId, payload)` | `deviceId: string`<br>`payload: object` | 更新结果 | `PUT /api/devices/{deviceId}/config` | `Settings.vue` |
| `updateBatchDeviceConfig(payload)` | `payload: object` | 批量更新结果 | `PUT /api/devices/batch-config` | `Settings.vue` |
| `getAlarmThresholds(deviceId)` | `deviceId: string` | 告警阈值对象 | `GET /api/devices/{deviceId}/alarm-thresholds` | `Settings.vue` |
| `updateAlarmThresholds(deviceId, payload)` | `deviceId: string`<br>`payload: object` | 更新结果 | `PUT /api/devices/{deviceId}/alarm-thresholds` | `Settings.vue` |

```javascript
// 使用示例
import { getDevices, getDeviceConfig, updateDeviceConfig } from '@/api/devices';

const devices = await getDevices();
const config = await getDeviceConfig('WTG-001');
await updateDeviceConfig('WTG-001', { sample_rate: 25600 });
```

### 2.8 api/alarms.js — 告警管理

**文件路径**：`src/api/alarms.js`（原 `api/alarm.js`，2026-11 更名）

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `getHistoryAlarmList(page, size, level, resolved, device_id)` | `page?: number`（默认 `1`）<br>`size?: number`（默认 `20`）<br>`level?: string`<br>`resolved?: boolean`<br>`device_id?: string` | 分页告警列表 | `GET /api/alarms/?page=...&size=...&level=...&resolved=...&device_id=...` | `Alarm.vue` |
| `updateAlarmStatus(alarmId)` | `alarmId: number \| string` | 更新结果 | `POST /api/alarms/{alarmId}/resolve` | `Alarm.vue` |
| `deleteAlarm(alarmId)` | `alarmId: number \| string` | 删除结果 | `DELETE /api/alarms/{alarmId}` | `Alarm.vue` |

```javascript
// 使用示例
import { getHistoryAlarmList, updateAlarmStatus, deleteAlarm } from '@/api/alarms';

const alarms = await getHistoryAlarmList(1, 20, 'critical', false, 'WTG-001');
await updateAlarmStatus(42);
await deleteAlarm(42);
```

### 2.9 api/system.js — 系统与采集

**文件路径**：`src/api/system.js`

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `getSystemLogs(lines)` | `lines?: number`（默认 `100`） | 日志文本数组 | `GET /api/logs/?lines=...` | `Logs.vue` |
| `requestCollection(deviceId)` | `deviceId: string` | 任务对象 `{ task_id }` | `POST /api/collect/request?device_id=...` | `Monitor.vue` |
| `getTaskStatus(taskId)` | `taskId: string` | 任务状态对象 | `GET /api/collect/tasks/{taskId}/status` | `Monitor.vue` |
| `getCollectionHistory(deviceId, limit)` | `deviceId?: string`（默认 `null`，不传则查所有设备）<br>`limit?: number`（默认 `20`） | `{ code, data: [{task_id, device_id, status, ...}] }` | `GET /api/collect/history?device_id=...&limit=...` | 预留（当前无视图调用） |

```javascript
// 使用示例
import { getSystemLogs, requestCollection, getTaskStatus } from '@/api/system';

const logs = await getSystemLogs(200);
const task = await requestCollection('WTG-001');
const status = await getTaskStatus(task.task_id);
```

### 2.10 api/acquisition.js — DC24 采集与实时示波

**文件路径**：`src/api/acquisition.js`

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `getAcquisitionAgents()` | 无 | 边端代理列表 | `GET /api/acquisition/agents` | `Acquisition.vue` |
| `getAcquisitionCapabilities()` | 无 | 服务能力（原厂采样率档位等） | `GET /api/acquisition/capabilities` | `Acquisition.vue` |
| `startLiveSession(data)` | `{ agent_id, sample_rate }` | 示波会话 | `POST /api/acquisition/sessions` | `Acquisition.vue` |
| `getLiveSession(id)` | `id: string` | 会话状态（404 静默） | `GET /api/acquisition/sessions/{id}` | `Acquisition.vue` |
| `getCurrentLiveSession(agent)` | `agent: string` | 边端当前会话（可为 `null`） | `GET /api/acquisition/agents/{agent}/session` | `Acquisition.vue` |
| `stopLiveSession(id)` | `id: string` | 停止后会话状态 | `POST /api/acquisition/sessions/{id}/stop` | `Acquisition.vue` |
| `getLiveView(id, params)` | `id: string`<br>`params: object`（波形/频谱/RMS/包络开关） | 实时窗口分析结果（错误静默） | `GET /api/acquisition/sessions/{id}/view` | `Acquisition.vue` |
| `startLiveRecording(id, data)` | `{ duration, save_directory, analysis }` | 保存任务 | `POST /api/acquisition/sessions/{id}/record` | `Acquisition.vue` |
| `stopLiveRecording(id)` | `id: string` | 停止保存 | `POST /api/acquisition/sessions/{id}/record/stop` | `Acquisition.vue` |
| `selectAcquisitionDirectory(agent)` | `agent: string` | 目录选择器 `{ id, status }` | `POST /api/acquisition/agents/{agent}/select-directory` | `Acquisition.vue` |
| `getAcquisitionDirectory(agent)` | `agent: string` | 目录选择结果 | `GET /api/acquisition/agents/{agent}/directory` | `Acquisition.vue` |
| `getAcquisitionJobs()` | 无 | 已保存任务列表 | `GET /api/acquisition/jobs` | `Acquisition.vue` |
| `createAcquisition(data)` | 任务参数 | 新任务 | `POST /api/acquisition/jobs` | 预留（回放任务族，当前无视图调用） |
| `getAcquisition(id)` | `id: string` | 任务详情 | `GET /api/acquisition/jobs/{id}` | 预留 |
| `stopAcquisition(id)` | `id: string` | 取消结果 | `POST /api/acquisition/jobs/{id}/cancel` | 预留 |
| `getAcquisitionAnalysis(id)` | `id: string` | 任务分析结果 | `GET /api/acquisition/jobs/{id}/analysis` | 预留 |
| `getAcquisitionWaveform(id, params)` | `id: string`<br>`params: object` | 波形数据 | `GET /api/acquisition/jobs/{id}/waveform` | 预留 |
| `downloadAcquisitionFile(id, name)` | `id: string`<br>`name: string` | 无（Blob 触发下载） | `GET /api/acquisition/jobs/{id}/files/{name}` | `Acquisition.vue` |

### 2.11 api/ingest.js — 边端数据接入（预留）

**文件路径**：`src/api/ingest.js`

`/api/ingest/` 由边端客户端（Rust `edge/`）调用，前端暂不直接调用；模块保留为占位说明，无导出函数。

---

## 3. Views 页面组件

> 所有页面组件位于 `src/views/` 目录下，通过 Vue Router 进行路由切换。以下按字母顺序列出。
>
> **2026-11-08（issue #50）拆分**：五大超长视图（DataView 2268 行、ResearchDiagnosis 778、Settings 693、Monitor 690、Dashboard 640）已拆分为「视图(薄壳) + `src/composables/` 逻辑 + `src/components/<view>/` 子组件」，视觉与行为零变化。下文各视图条目中的"关键状态/关键方法"已移入对应 composable（见第 6 节），视图本身仅保留组合与布局。

### 3.1 Alarm.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/views/Alarm.vue` |
| **用途** | 告警历史列表展示、筛选、标记已处理、删除及跳转到关联数据 |

**关键状态（`data` / `setup`）**

| 状态名 | 类型 | 说明 |
|--------|------|------|
| `alarmList` | `Array` | 当前页告警列表 |
| `total` | `number` | 告警总条数 |
| `currentPage` | `number` | 当前页码 |
| `pageSize` | `number` | 每页条数 |
| `filterLevel` | `string` | 告警级别筛选（如 `critical` / `warning`） |
| `filterDevice` | `string` | 按设备 ID 筛选 |

**关键方法**

| 方法名 | 说明 |
|--------|------|
| `loadData()` | 加载告警列表（带分页与筛选） |
| `loadDeviceList()` | 加载设备列表供筛选下拉框使用 |
| `handleResolve(alarmId)` | 将告警标记为已处理 |
| `handleDelete(alarmId)` | 删除单条告警 |
| `handleViewData(deviceId, batchIndex)` | 跳转到对应设备的 `DataView` 页面查看原始数据 |

**调用 API**

```javascript
import { getHistoryAlarmList, updateAlarmStatus, deleteAlarm } from '@/api/alarms';
import { getDevices } from '@/api/devices';
```

---

### 3.2 Dashboard.vue

**2026-10-21 生命周期与刷新约定**：卸载钩子在 setup 同步注册，退出时取消订阅、60 秒轮询和 resize 监听并销毁图表；等待请求/nextTick 期间退出，不再初始化资源。刷新后按 `deviceId` 重新绑定选中设备，仪表盘不再引用旧对象。状态 `critical` 与原有 `fault` 均显示为故障并纳入故障计数。

`loadData()` 将首次加载、上线/离线推送和轮询串行执行；请求期间的事件合并为一次后续查询。若当前请求失败但已有待刷新事件，记录错误并继续查询；没有后续事件时向调用方抛出错误并释放刷新状态。卸载后丢弃响应和待刷新事件。

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/views/Dashboard.vue` |
| **用途** | 系统总览面板，展示设备在线状态、健康度仪表盘、告警统计饼图 |

**关键状态**

| 状态名 | 类型 | 说明 |
|--------|------|------|
| `devices` | `Array` | 设备列表及状态 |
| `selectedDevice` | `object \| null` | 当前选中的设备 |
| `alarmStats` | `object` | 告警统计数据（各级别数量） |
| `gaugeChart` | `ECharts Instance` | 健康度仪表盘实例 |
| `pieChart` | `ECharts Instance` | 告警分布饼图实例 |

**关键方法**

| 方法名 | 说明 |
|--------|------|
| `loadData()` | 串行加载设备总览与告警统计，合并在途刷新；返回整轮刷新 Promise |
| `fetchDashboardData()` | 执行一次总览查询并更新设备、统计和当前选中对象 |
| `selectDevice(device)` | 选中设备并更新仪表盘数据 |
| `initGaugeChart()` | 初始化健康度仪表盘 |
| `initPieChart()` | 初始化告警饼图 |

**调用 API**

```javascript
import { getDeviceInfo } from '@/api';
```

**WebSocket 事件**

| 事件名 | 说明 |
|--------|------|
| `device_online` | 设备上线时刷新列表 |
| `device_offline` | 设备下线时刷新列表 |

---

### 3.3 DataView.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/views/DataView.vue` |
| **用途** | 最核心的数据分析页面，支持时域/频域/时频/包络/阶次/倒谱/齿轮/全分析等多维度查看与诊断 |

**关键状态**

| 状态名 | 类型 | 说明 |
|--------|------|------|
| `loading` | `boolean` | 全局加载状态 |
| `selectedDevice` | `string` | 当前选中设备 ID |
| `selectedBatch` | `number` | 当前选中批次号 |
| `selectedChannel` | `number` | 当前选中通道号（1/2/3...） |
| `maxFreq` | `number` | 频谱显示最大频率 |
| `enableDetrend` | `boolean` | 是否去趋势 |
| `denoiseMethod` | `string` | 去噪方式（`none` / `wavelet` / `vmd` / `med`） |

**关键方法**

| 方法名 | 说明 |
|--------|------|
| `loadAllDevices()` | 加载所有设备及批次列表 |
| `selectBatch(batchIndex)` | 切换批次并加载时域数据 |
| `loadTimeDomain()` | 加载时域波形 |
| `computeFFT()` | 计算并展示 FFT 频谱 |
| `computeSTFT()` | 计算并展示 STFT 时频图 |
| `computeEnvelope()` | 计算并展示包络谱 |
| `computeOrder()` | 计算并展示阶次谱 |
| `computeGear()` | 计算并展示齿轮诊断指标 |
| `computeFullAnalysis()` | 执行全算法分析 |
| `computeStats()` | 计算并展示统计指标 |
| `onReanalyze()` | 对当前批次发起重新诊断 |
| `onReanalyzeAll()` | 对当前设备全部批次重新诊断 |
| `onDeleteBatch()` | 删除当前批次 |
| `gotoResearchDiagnosis()` | 跳转到研究级诊断页面 |

**调用 API**

```javascript
import {
  getDeviceBatches,
  getChannelData,
  getChannelFFT,
  getChannelSTFT,
  getChannelEnvelope,
  getChannelGear,
  getChannelAnalyze,
  getChannelFullAnalysis,
  getChannelDiagnosis,
  getChannelOrder,
  getChannelCepstrum,
  getChannelStats,
  deleteBatch,
  deleteSpecialBatches,
  exportChannelCSV
} from '@/api/data';
import {
  getChannelAnalyze,
  getChannelFullAnalysis,
  getChannelDiagnosis,
  updateBatchDiagnosis,
  reanalyzeBatch,
  reanalyzeAllDevice
} from '@/api/diagnosis';
```

---

### 3.4 Login.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/views/Login.vue` |
| **用途** | 系统登录页，输入密码获取 JWT Token |

**关键状态**

| 状态名 | 类型 | 说明 |
|--------|------|------|
| `form.password` | `string` | 用户输入的密码 |
| `loading` | `boolean` | 登录请求中状态 |

**关键方法**

| 方法名 | 说明 |
|--------|------|
| `handleLogin()` | 调用登录 API，成功后保存 `token` 并跳转首页 |

**调用 API**

```javascript
import { login } from '@/api/auth';
```

---

### 3.5 Logs.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/views/Logs.vue` |
| **用途** | 系统日志实时查看，支持定时轮询刷新 |

**关键状态**

| 状态名 | 类型 | 说明 |
|--------|------|------|
| `logs` | `Array<string>` | 日志行数组 |
| `error` | `string \| null` | 加载错误信息 |
| `loading` | `boolean` | 加载状态 |
| `lines` | `number` | 每次拉取的日志行数 |
| `timer` | `number \| null` | 5 秒轮询定时器 ID |

**关键方法**

| 方法名 | 说明 |
|--------|------|
| `fetchLogs()` | 拉取最新系统日志并更新列表 |

**调用 API**

```javascript
import { getSystemLogs } from '@/api/system';
```

---

### 3.6 Monitor.vue

**2026-10-21 请求调度**：WebSocket 只响应当前设备的事件，将 100 ms 内的连续事件合并；同一页面最多一个监测刷新请求在途，在途事件保留一次后续刷新。`refreshLatestData(preferSpecial=false)` 供初始化、设备切换和采集完成复用，后续刷新保留特殊采集优先请求。切换设备后丢弃旧设备响应，通道数减少时重置无效通道选择，空数据清空图表。卸载取消待执行定时器。

**采集轮询**：完成一次状态查询后再等待 2 秒，避免慢请求重叠；卸载后忽略响应且不再安排下一轮。成功/失败/最多 60 次的终止条件保留。

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/views/Monitor.vue` |
| **用途** | 实时振动监控页面，支持手动采集任务、实时波形/频谱展示 |

**关键状态**

| 状态名 | 类型 | 说明 |
|--------|------|------|
| `activeChannel` | `number` | 当前活动通道 |
| `channels` | `Array` | 通道列表 |
| `params` | `object` | 显示参数配置 |
| `timeDomainChart` | `ECharts Instance` | 时域波形图实例 |
| `frequencyChart` | `ECharts Instance` | 频谱图实例 |
| `isCollecting` | `boolean` | 是否正在采集 |
| `collectionStatus` | `string` | 采集任务状态文本 |
| `collectionProgress` | `number` | 采集进度百分比 |

**关键方法**

| 方法名 | 说明 |
|--------|------|
| `loadCollectDevices()` | 加载可用于采集的设备列表 |
| `requestCollect()` | 发起手动采集请求 |
| `startPolling(taskId)` | 启动任务状态轮询 |
| `loadLatestData()` | 加载最新实时振动数据 |
| `updateCharts()` | 更新时域和频谱图表 |
| `initCharts()` | 挂载后先创建时域和频谱实例，再加载设备和波形数据 |
| `setupWebSocket()` | 注册具名推送回调；离开页面时移除订阅并关闭连接 |
| `handleResize()` | 调整图表尺寸；随页面挂载注册、卸载移除 |

**生命周期约定（2026-10-19 修复）**：首次进入和路由返回均先初始化图表，再请求数据并绘制默认通道，无需手动切换通道。`onUnmounted` 在 setup 阶段同步注册，清理采集轮询、WebSocket 订阅、图表实例及 resize 监听；异步初始化和波形请求在页面卸载后不再继续建立连接或绘图。波形读取云端数据库中的已有记录，显示波形不代表本机边端正在采集。

**WebSocket 工具约定（2026-10-21）**：`utils/websocket.js` 的 `connect()` 对 OPEN/CONNECTING 均幂等；旧连接的迟到回调不影响新连接。重连定时器和心跳各最多一个，主动 close 禁止安排重连；`on/off` 的现有接口保持兼容。

**调用 API**

```javascript
import { getRealtimeVibrationData } from '@/api/monitor';
import { requestCollection, getTaskStatus } from '@/api/system';
import { getDevices } from '@/api/devices';
```

**WebSocket 事件**

| 事件名 | 说明 |
|--------|------|
| `sensor_update` | 收到新的传感器数据，更新图表 |
| `diagnosis_update` | 收到新的诊断结果，更新状态展示 |

---

### 3.7 ResearchDiagnosis.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/views/ResearchDiagnosis.vue` |
| **用途** | 研究级诊断页面，支持单方法分析、多方法集成分析（profile 模式） |

**关键状态**

| 状态名 | 类型 | 说明 |
|--------|------|------|
| `devices` | `Array` | 设备列表（含批次） |
| `selectedDeviceId` | `string` | 选中设备 ID |
| `selectedBatchIndex` | `number` | 选中批次号 |
| `selectedChannel` | `number` | 选中通道号 |
| `runMode` | `string` | 运行模式（`single` 单方法 / `profile` 集成分析） |
| `selectedMethod` | `string` | 单方法模式下选中的分析方法 |
| `denoise` | `string` | 去噪方式 |
| `profile` | `string` | 集成分析配置名 |

**关键方法**

| 方法名 | 说明 |
|--------|------|
| `loadDevices()` | 加载所有设备及批次 |
| `loadMethodInfo()` | 加载可用分析方法列表 |
| `runAnalysis()` | 根据 `runMode` 执行单方法分析或集成分析 |

**调用 API**

```javascript
import {
  getAllDeviceData
} from '@/api/data';
import {
  getMethodInfo,
  getChannelMethodAnalysis,
  getChannelResearchAnalysis
} from '@/api/diagnosis';
```

---

### 3.8 Settings.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/views/Settings.vue` |
| **用途** | 系统设置页，管理设备配置、机械参数、告警阈值，支持批量配置 |

**关键状态**

| 状态名 | 类型 | 说明 |
|--------|------|------|
| `deviceList` | `Array` | 设备下拉列表 |
| `form` | `object` | 当前设备的表单数据（配置项） |
| `thresholds` | `object` | 当前设备的告警阈值 |
| `activeMechanicalChannel` | `number` | 当前正在编辑机械参数的通道 |

**关键方法**

| 方法名 | 说明 |
|--------|------|
| `loadDevices()` | 加载设备列表 |
| `onDeviceChange(deviceId)` | 切换设备时加载其配置与阈值 |
| `onSaveEdgeConfig()` | 保存边端/设备基础配置 |
| `onSaveMechanical()` | 保存机械参数（轴承/齿轮参数） |
| `onSaveThresholds()` | 保存告警阈值 |

**调用 API**

```javascript
import {
  getDevices,
  getDeviceConfig,
  updateDeviceConfig,
  updateBatchDeviceConfig,
  getAlarmThresholds,
  updateAlarmThresholds
} from '@/api/devices';
```

---

### 3.9 Acquisition.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/views/Acquisition.vue` |
| **用途** | DC24 实时示波与采集:选择现场边端与采样率开始示波,四通道波形/频谱/RMS/包络实时显示,随时开始/停止原始数据保存 |

**实时窗口数据流（2026-11-08,issue #51）**：会话激活时经 `utils/websocket.js::createWebSocketClient` 订阅 `WS /ws/acquisition/sessions/{id}/view`;连接建立即发送当前分析选项(显示开关/时间窗/包络带),`view` 推送驱动 ECharts 绘制,`session` 推送更新会话状态;WS 未连上时回退 `api/acquisition.js::getLiveView` REST 轮询,断线由客户端指数退避重连,会话停止/404 恢复/页面卸载时关闭订阅。

**调用 API**：`api/acquisition.js` 全部函数(见 2.10 节)。

---

## 4. Components 通用组件

> 2026-11-08 起组件目录分两层：`src/components/` 通用组件（本节）与 `src/components/<view>/` 页面专属子组件（dashboard/、monitor/、settings/、research/、dataview/ 下各节，Props/Emits 见源码头部 defineProps/defineEmits/defineModel 声明）。

> 所有通用组件位于 `src/components/` 目录下，供多个页面复用。

### 4.1 Layout.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/components/Layout.vue` |
| **用途** | 系统整体布局，包含侧边导航栏、顶部栏、内容区插槽 |

**Props**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| （无显著对外 Props） | — | — | 主要通过路由和内部状态管理导航 |

**Emits**

| 事件名 | 说明 |
|--------|------|
| （无显著对外 Emits） | — |

**关键方法**

| 方法名 | 说明 |
|--------|------|
| `handleMenuSelect(index)` | 菜单选中切换路由 |
| `handleLogout()` | 退出登录，清除 Token 并跳转登录页 |

---

### 4.2 VibrationChart.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/components/VibrationChart.vue` |
| **用途** | 基于 ECharts 的振动数据图表封装，统一处理图表初始化与自适应 |

**Props**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `option` | `object` | `{}` | ECharts 配置项对象 |
| `height` | `string \| number` | `'300px'` | 图表容器高度 |

**Emits**

| 事件名 | 说明 |
|--------|------|
| （通常不对外触发事件） | — |

---

### 4.3 DiagnosisDetail.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/components/DiagnosisDetail.vue` |
| **用途** | 诊断结果明细展示，包括阶次分析、转频、健康度、故障概率、轴承包络评估与 SC/SCoh 专属指标 |

**Props**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `orderAnalysis` | `object \| null` | `null` | 阶次/包络/频谱分析明细对象 |
| `rotFreq` | `number \| null` | `null` | 估计转频（Hz） |
| `rotRpm` | `number \| null` | `null` | 估计转速（RPM） |

**数据读取约定**：轴承评估行与特征频率分别读取 `bearing.evaluation.indicators` 的 `value/score/snr/significant` 和 `theory_hz/detected_hz`；只有真实峰值/背景比显示为 SNR，其他强度显示为 score。SC/SCoh 独立读取 `bearing.sc_scoh_indicators` 的 `theory_hz/scoh_peak/scoh_snr/significant/warning/critical`。齿轮仍读取 `gear.fault_indicators`，两套契约不得互相替换。

**Emits**

| 事件名 | 说明 |
|--------|------|
| （通常纯展示组件） | — |

**内部方法**

| 方法名 | 说明 |
|--------|------|
| `faultLabelText` | 故障类型中文标签映射 |
| `statusTagType` | 状态转 Element Plus 标签类型 |
| `scoreClass` | 健康度分数 CSS 类名映射 |
| `statusText` | 状态文本映射（含空值保护） |
| `fmtVal` | 数值格式化（保留小数 + 空值显示 `-`） |

---

### 4.4 DetailHeader.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/components/DetailHeader.vue` |
| **用途** | 数据详情页头部工具栏，包含设备/批次/通道选择器、操作按钮 |

**Props**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| （大量 Props，典型如下） | — | — | — |
| `devices` | `Array` | `[]` | 设备列表 |
| `selectedDevice` | `string` | `''` | 当前选中设备 |
| `batches` | `Array` | `[]` | 批次列表 |
| `selectedBatch` | `number` | `null` | 当前选中批次 |
| `channels` | `Array` | `[]` | 通道列表 |
| `selectedChannel` | `number` | `1` | 当前选中通道 |
| `loading` | `boolean` | `false` | 加载状态 |

**Emits**

| 事件名 | 说明 |
|--------|------|
| `update:selectedDevice` | 设备切换 |
| `update:selectedBatch` | 批次切换 |
| `update:selectedChannel` | 通道切换 |
| `reanalyze` | 点击重新诊断按钮 |
| `reanalyzeAll` | 点击全部重新诊断按钮 |
| `deleteBatch` | 点击删除批次按钮 |
| `exportCsv` | 点击导出 CSV 按钮 |

---

### 4.5 DeviceTable.vue

| 属性 | 说明 |
|------|------|
| **文件路径** | `src/components/DeviceTable.vue` |
| **用途** | 设备批次数据表格展示，支持加载状态 |

**Props**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `data` | `Array` | `[]` | 表格数据（批次列表） |
| `loading` | `boolean` | `false` | 表格加载状态 |

**Emits**

| 事件名 | 说明 |
|--------|------|
| `rowClick` | 点击某一行时触发，通常携带批次信息 |
| `batchSelect` | 选中某个批次 |

---

## 5. WebSocket 事件汇总

前端通过 WebSocket 与后端建立长连接，监听以下事件实现实时推送：

| 事件名 | 来源页面 | 说明 |
|--------|----------|------|
| `device_online` | `Dashboard.vue` | 设备上线通知，刷新设备列表 |
| `device_offline` | `Dashboard.vue` | 设备离线通知，刷新设备列表 |
| `sensor_update` | `Monitor.vue` | 实时传感器数据更新，驱动图表刷新 |
| `diagnosis_update` | `Monitor.vue` | 实时诊断结果更新，展示最新健康状态 |

> **注意**：WebSocket 连接通常在 `app/main.py` 的 `/ws` 端点建立，前端通过原生 `WebSocket` 或封装库进行订阅。

---

> **文档结束**。如有接口变更，请务必同步更新本文件，保持与代码的一致性。

---

## 6. Composables 组合式函数（2026-11 拆分）

> 五大视图的业务逻辑层，位于 `src/composables/`。均在视图 `setup` 中调用一次，内部注册生命周期钩子（挂载加载/卸载清理），返回响应式状态与方法；模块级具名导出为跨组件共享的常量与工具。

| 文件 | 服务视图 | 返回内容(概要) | 模块级导出 |
|------|---------|---------------|-----------|
| `useDashboard.js` | `Dashboard.vue` | `devices/selectedDevice` 等状态、`loadData()`(推送+轮询共享串行刷新)、`selectDevice()`、图表 ref(`gaugeChart/pieChart`)、状态映射工具 | `getStatusType/getStatusText/getHealthColor`(Dashboard 专属口径:critical 计故障、85/60 分档,勿与 utils/status.js 混用) |
| `useMonitor.js` | `Monitor.vue` | `channels/params/sensors/collectDevices`、`requestCollect()`、`startPolling(taskId)`、`refreshLatestData()`(推送合并串行)、`onMonitorDeviceChange()`、图表 ref | — |
| `useSettings.js` | `Settings.vue` | `form/channelNames/thresholds/thresholdEnabled`、三级加载、`onSaveEdgeConfig/onSaveMechanical/onSaveThresholds/onSyncMechanical`、`intervalValue/intervalUnit` 与 `computedSeconds` | `unitOptions`(采集间隔单位)、`thresholdItems`(阈值指标定义) |
| `useResearchDiagnosis.js` | `ResearchDiagnosis.vue` | 三级选择器、`runAnalysis()`(single/all/ensemble)、`gotoDataView()`、投票行/D-S 融合行/全方法摘要行等派生 computed；轴承行读取 `evaluation/sc_scoh_indicators`，齿轮行保留 `fault_indicators` | `runModeOptions`、`fmt/percent/statusType/statusText`、`evaluationStatusType/evaluationStatusText` |
| `useDataView.js` | `DataView.vue` | 设备批次表格数据与选择、时域自动加载、FFT/STFT/结构化包络谱/阶次/倒谱/统计/齿轮 `computeX/clearX`、轴承与齿轮特征频率标注、综合/策略诊断、删除/重新诊断/导出、路由联动 | `bearingMethodLabel`、`statsGroups`、`statsDisplay`(预留) |

**配套子组件目录**：`src/components/dashboard/`(SummaryCards、DeviceCardList)、`src/components/monitor/`(SensorStatusCard、RunParamsCard、CollectionProgress)、`src/components/settings/`(EdgeConfigCard、MechanicalParamsCard、ThresholdsCard、ConfigNotesCard)、`src/components/research/`(ResearchToolbar、SingleResultPanels、EnsembleResultPanels)、`src/components/dataview/`(StatsSection、FftEnvelopeSection、GearSection、ComprehensiveSection、OrderSection、CepstrumSection、StftSection、DiagnosisDetailSection)。

**轴承包络适配点**：`FftEnvelopeSection` 展示实际频带、评估状态与 SC/SCoh 命中数；`ComprehensiveSection` 的轴承汇总和详细指标读取新契约；`SingleResultPanels` 分组展示实际频带、`features`、包络评估指标和 SC/SCoh 专属指标；`EnsembleResultPanels` 与 `ResearchDiagnosis.vue` 对 `indeterminate` 显示“不可判定”，对 `not_evaluable` 显示“不可评估”，均不视为正常。投票强度读取 `strongest_score`。这些组件通过 `utils/bearingDiagnosis.js` 统一派生轴承条目，不改变齿轮/行星箱面板的数据路径。

**回归测试约定**：`tests/dashboard_lifecycle.test.cjs`、`tests/monitor_lifecycle.test.cjs` 在同一 VM 上下文装载 composable 源码并以空壳桩替换子组件标识符,断言语义与拆分前一致;修改 composable 时两套测试必须保持全绿。`tests/bearing_contract.test.cjs` 直接验证结构化包络图 option、轴承/SC/齿轮标注与汇总，并通过 SFC 编译后的 `setup` 验证 `DiagnosisDetail` 和 `SingleResultPanels` 的派生数据；修改轴承响应读取逻辑后必须运行该测试及完整 `node --test tests/*.test.cjs`。
