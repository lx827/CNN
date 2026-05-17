# 前端接口文档

> **文档用途**：汇总 `wind-turbine-diagnosis` 前端项目中的所有 API 封装、Vue 页面组件及通用组件的接口定义，便于前后端联调与后续维护。  
> **维护提醒**：每当新增/修改 API 或组件 Props/Emits 时，请同步更新本文档。文档应与代码保持一致，避免口头约定。

---

## 目录

1. [Axios 基础配置](#1-axios-基础配置)
2. [API 层](#2-api-层)
   - 2.1 [api/index.js — 认证与监控](#21-apiindexjs--认证与监控)
   - 2.2 [api/data.js — 数据查看与诊断](#22-apidatajs--数据查看与诊断)
   - 2.3 [api/device.js — 设备配置](#23-apidevicejs--设备配置)
   - 2.4 [api/alarm.js — 告警管理](#24-apialarmjs--告警管理)
   - 2.5 [api/system.js — 系统与采集](#25-apisystemjs--系统与采集)
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

### 2.1 api/index.js — 认证与监控

**文件路径**：`src/api/index.js`

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `login(password)` | `password: string` | `{ token: string }` | `POST /api/auth/login` | `Login.vue` |
| `getDeviceInfo()` | 无 | 设备总览数据对象 | `GET /api/dashboard/` | `Dashboard.vue` |
| `getRealtimeVibrationData(device_id, prefer_special, limit)` | `device_id: string`<br>`prefer_special?: boolean`（默认 `true`）<br>`limit?: number`（默认 `1024`） | 实时振动数据数组 | `GET /api/monitor/latest?device_id=...&prefer_special=...&limit=...` | `Monitor.vue` |

```javascript
// 使用示例
import { login, getDeviceInfo, getRealtimeVibrationData } from '@/api';

await login('admin123');
const info = await getDeviceInfo();
const data = await getRealtimeVibrationData('WTG-001', true, 2048);
```

---

### 2.2 api/data.js — 数据查看与诊断

**文件路径**：`src/api/data.js`

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `getDeviceBatches(deviceId)` | `deviceId: string` | 批次列表 | `GET /api/data/{deviceId}/batches` | `DataView.vue`, `DeviceTable.vue` |
| `getChannelData(deviceId, batchIndex, channel)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number` | 时域数据点数组 | `GET /api/data/{deviceId}/{batchIndex}/{channel}` | `DataView.vue` |
| `getChannelFFT(deviceId, batchIndex, channel, max_freq)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`max_freq?: number` | FFT 频谱数据 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/fft?max_freq=...` | `DataView.vue` |
| `getChannelSTFT(deviceId, batchIndex, channel, max_freq, nperseg, noverlap)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`max_freq?: number`<br>`nperseg?: number`<br>`noverlap?: number` | STFT 时频图数据 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/stft?...` | `DataView.vue` |
| `getChannelEnvelope(deviceId, batchIndex, channel, max_freq, method, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`max_freq?: number`<br>`method?: string`<br>`denoise?: string` | 包络谱数据 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/envelope?...` | `DataView.vue` |
| `getChannelGear(deviceId, batchIndex, channel, method, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`method?: string`<br>`denoise?: string` | 齿轮诊断指标 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/gear?...` | `DataView.vue` |
| `getChannelAnalyze(deviceId, batchIndex, channel, strategy, bearing_method, gear_method, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`strategy?: string`<br>`bearing_method?: string`<br>`gear_method?: string`<br>`denoise?: string` | 综合分析结果 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/analyze?...` | `DataView.vue` |
| `getChannelFullAnalysis(deviceId, batchIndex, channel, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`denoise?: string` | 全算法分析结果 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/full-analysis?denoise=...` | `DataView.vue` |
| `getChannelResearchAnalysis(deviceId, batchIndex, channel, profile, denoise, max_seconds)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`profile?: string`<br>`denoise?: string`<br>`max_seconds?: number` | 研究级分析结果 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/research-analysis?...` | `ResearchDiagnosis.vue` |
| `getChannelDiagnosis(deviceId, batchIndex, channel, denoise_method)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`denoise_method?: string` | 诊断缓存结果 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/diagnosis?denoise_method=...` | `DataView.vue`, `DiagnosisDetail.vue` |
| `getChannelOrder(deviceId, batchIndex, channel, freq_min, freq_max, samples_per_rev, max_order, rot_freq)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`freq_min?: number`<br>`freq_max?: number`<br>`samples_per_rev?: number`<br>`max_order?: number`<br>`rot_freq?: number` | 阶次谱数据 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/order?...` | `DataView.vue` |
| `getChannelCepstrum(deviceId, batchIndex, channel, max_quefrency)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`max_quefrency?: number` | 倒谱数据 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/cepstrum?max_quefrency=...` | `DataView.vue` |
| `getChannelStats(deviceId, batchIndex, channel, window_size, step)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`window_size?: number`<br>`step?: number` | 统计指标数据 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/stats?...` | `DataView.vue` |
| `getMethodInfo()` | 无 | 可用分析方法列表 | `GET /api/data/method-info` | `ResearchDiagnosis.vue` |
| `getChannelMethodAnalysis(deviceId, batchIndex, channel, method, denoise)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number`<br>`method: string`<br>`denoise?: string` | 单方法分析结果 | `GET /api/data/{deviceId}/{batchIndex}/{channel}/method-analysis?method=...&denoise=...` | `ResearchDiagnosis.vue` |
| `updateBatchDiagnosis(deviceId, batchIndex, order_analysis, rot_freq)` | `deviceId: string`<br>`batchIndex: number`<br>`order_analysis: object`<br>`rot_freq?: number` | 更新结果 | `PUT /api/data/{deviceId}/{batchIndex}/diagnosis` | `DataView.vue` |
| `reanalyzeBatch(deviceId, batchIndex)` | `deviceId: string`<br>`batchIndex: number` | 重新诊断结果 | `POST /api/data/{deviceId}/{batchIndex}/reanalyze` | `DataView.vue` |
| `reanalyzeAllDevice(deviceId)` | `deviceId: string` | 批量重新诊断汇总 | `POST /api/data/{deviceId}/reanalyze-all` | `DataView.vue` |
| `getAllDeviceData()` | 无 | 所有设备及批次数据 | `GET /api/data/devices` | `ResearchDiagnosis.vue` |
| `deleteBatch(deviceId, batchIndex)` | `deviceId: string`<br>`batchIndex: number` | 删除结果 | `DELETE /api/data/{deviceId}/{batchIndex}` | `DataView.vue` |
| `deleteSpecialBatches(deviceId)` | `deviceId: string` | 删除结果 | `DELETE /api/data/{deviceId}/special` | `DataView.vue` |
| `exportChannelCSV(deviceId, batchIndex, channel)` | `deviceId: string`<br>`batchIndex: number`<br>`channel: number` | Blob（CSV 文件流） | `GET /api/data/{deviceId}/{batchIndex}/{channel}/export` | `DataView.vue` |

```javascript
// 典型调用示例
import {
  getChannelFFT,
  getChannelFullAnalysis,
  reanalyzeBatch,
  exportChannelCSV
} from '@/api/data';

const fft = await getChannelFFT('WTG-001', 1, 1, 5000);
const full = await getChannelFullAnalysis('WTG-001', 1, 1, 'wavelet');
await reanalyzeBatch('WTG-001', 1);
const blob = await exportChannelCSV('WTG-001', 1, 1);
```

---

### 2.3 api/device.js — 设备配置

**文件路径**：`src/api/device.js`

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
import { getDevices, getDeviceConfig, updateDeviceConfig } from '@/api/device';

const devices = await getDevices();
const config = await getDeviceConfig('WTG-001');
await updateDeviceConfig('WTG-001', { sample_rate: 25600 });
```

---

### 2.4 api/alarm.js — 告警管理

**文件路径**：`src/api/alarm.js`

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `getHistoryAlarmList(page, size, level, resolved, device_id)` | `page?: number`（默认 `1`）<br>`size?: number`（默认 `20`）<br>`level?: string`<br>`resolved?: boolean`<br>`device_id?: string` | 分页告警列表 | `GET /api/alarms/?page=...&size=...&level=...&resolved=...&device_id=...` | `Alarm.vue` |
| `updateAlarmStatus(alarmId)` | `alarmId: number \| string` | 更新结果 | `POST /api/alarms/{alarmId}/resolve` | `Alarm.vue` |
| `deleteAlarm(alarmId)` | `alarmId: number \| string` | 删除结果 | `DELETE /api/alarms/{alarmId}` | `Alarm.vue` |

```javascript
// 使用示例
import { getHistoryAlarmList, updateAlarmStatus, deleteAlarm } from '@/api/alarm';

const alarms = await getHistoryAlarmList(1, 20, 'critical', false, 'WTG-001');
await updateAlarmStatus(42);
await deleteAlarm(42);
```

---

### 2.5 api/system.js — 系统与采集

**文件路径**：`src/api/system.js`

| 函数名 | 参数 | 返回值 | 后端 URL | 调用组件 |
|--------|------|--------|----------|----------|
| `getSystemLogs(lines)` | `lines?: number`（默认 `100`） | 日志文本数组 | `GET /api/logs/?lines=...` | `Logs.vue` |
| `requestCollection(deviceId, sample_rate, duration)` | `deviceId: string`<br>`sample_rate?: number`<br>`duration?: number` | 任务对象 `{ task_id }` | `POST /api/collect/request` | `Monitor.vue` |
| `getTaskStatus(taskId)` | `taskId: string` | 任务状态对象 | `GET /api/collect/tasks/{taskId}/status` | `Monitor.vue` |

```javascript
// 使用示例
import { getSystemLogs, requestCollection, getTaskStatus } from '@/api/system';

const logs = await getSystemLogs(200);
const task = await requestCollection('WTG-001', 25600, 10);
const status = await getTaskStatus(task.task_id);
```

---

## 3. Views 页面组件

> 所有页面组件位于 `src/views/` 目录下，通过 Vue Router 进行路由切换。以下按字母顺序列出。

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
import { getHistoryAlarmList, updateAlarmStatus, deleteAlarm } from '@/api/alarm';
import { getDevices } from '@/api/device';
```

---

### 3.2 Dashboard.vue

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
| `loadData()` | 加载设备总览与告警统计 |
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
  updateBatchDiagnosis,
  reanalyzeBatch,
  reanalyzeAllDevice,
  deleteBatch,
  deleteSpecialBatches,
  exportChannelCSV
} from '@/api/data';
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
import { login } from '@/api';
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

**调用 API**

```javascript
import { getRealtimeVibrationData } from '@/api';
import { requestCollection, getTaskStatus } from '@/api/system';
import { getDevices } from '@/api/device';
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
  getAllDeviceData,
  getMethodInfo,
  getChannelMethodAnalysis,
  getChannelResearchAnalysis
} from '@/api/data';
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
} from '@/api/device';
```

---

## 4. Components 通用组件

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
| **用途** | 诊断结果明细展示，包括阶次分析、转频、健康度、故障概率等 |

**Props**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `orderAnalysis` | `object \| null` | `null` | 阶次/包络/频谱分析明细对象 |
| `rotFreq` | `number \| null` | `null` | 估计转频（Hz） |
| `rotRpm` | `number \| null` | `null` | 估计转速（RPM） |

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
