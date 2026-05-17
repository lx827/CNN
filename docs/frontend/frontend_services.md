# 前端服务层与工具函数接口文档

> **文档用途**：完整记录前端 `stores/`、`utils/` 和 `components/` 目录下的所有模块接口，便于 AI Agent 快速定位和修改代码。
> **维护要求**：新增、修改或删除任何公共函数/组件时，必须同步更新本文档。

---

## 目录

1. [状态管理 (Stores)](#1-状态管理-stores)
2. [工具函数 (Utils)](#2-工具函数-utils)
3. [通用组件 (Components)](#3-通用组件-components)
4. [路由配置](#4-路由配置)

---

## 1. 状态管理 (Stores)

> 使用 Pinia 进行状态管理，所有 Store 位于 `src/stores/` 目录下。

### 1.1 用户状态 (`userStore.js`)

**文件路径**：`src/stores/userStore.js`

| 属性/方法 | 类型 | 说明 |
|-----------|------|------|
| `state.token` | `string \| null` | JWT Token |
| `state.isLoggedIn` | `computed` | 是否已登录 |
| `login(token)` | `Action` | 保存 Token 到 localStorage 和 state |
| `logout()` | `Action` | 清除 Token 和状态 |
| `initToken()` | `Action` | 从 localStorage 初始化 Token |

### 1.2 设备状态 (`deviceStore.js`)

**文件路径**：`src/stores/deviceStore.js`

| 属性/方法 | 类型 | 说明 |
|-----------|------|------|
| `state.devices` | `Array` | 设备列表 |
| `state.selectedDevice` | `object \| null` | 当前选中设备 |
| `state.batches` | `Array` | 当前设备的批次列表 |
| `state.selectedBatch` | `number \| null` | 当前选中批次号 |
| `state.selectedChannel` | `number` | 当前选中通道号（默认 1） |
| `setDevices(devices)` | `Action` | 更新设备列表 |
| `selectDevice(device)` | `Action` | 选中设备 |
| `setBatches(batches)` | `Action` | 更新批次列表 |
| `selectBatch(batchIndex)` | `Action` | 选中批次 |
| `setChannel(channel)` | `Action` | 切换通道 |

### 1.3 Store 入口 (`index.js`)

**文件路径**：`src/stores/index.js`

```javascript
// 使用方式
import { useUserStore, useDeviceStore } from '@/stores';

const userStore = useUserStore();
const deviceStore = useDeviceStore();
```

---

## 2. 工具函数 (Utils)

### 2.1 Axios 请求封装 (`request.js`)

**文件路径**：`src/utils/request.js`

| 配置/拦截器 | 说明 |
|-------------|------|
| `baseURL` | 动态获取当前 host（开发环境通过 Vite 代理） |
| 请求拦截器 | 从 `localStorage` 读取 `token`，注入 `Authorization: Bearer {token}` |
| 响应拦截器 | `code !== 200` 抛错；`401` 清除 Token 并跳转登录页 |

```javascript
// 使用方式
import request from '@/utils/request';

request.get('/api/dashboard/').then(res => { ... });
request.post('/api/auth/login', { password: 'xxx' }).then(res => { ... });
```

### 2.2 WebSocket 工具 (`websocket.js`)

**文件路径**：`src/utils/websocket.js`

| 函数/属性 | 类型 | 说明 |
|-----------|------|------|
| `ws` | `WebSocket \| null` | WebSocket 实例 |
| `wsConnected` | `ref<boolean>` | 连接状态 |
| `getWebSocketClient` | `() -> WebSocketClient` | 获取单例 WebSocket 客户端实例 |
| `connect()` | `Function` | 建立 WebSocket 连接 |
| `disconnect()` | `Function` | 断开连接 |
| `send(data)` | `Function` | 发送消息 |
| `on(event, callback)` | `Function` | 注册事件监听器 |
| `off(event, callback)` | `Function` | 移除事件监听器 |

**支持的事件类型**：

| 事件名 | 说明 |
|--------|------|
| `device_online` | 设备上线 |
| `device_offline` | 设备离线 |
| `sensor_update` | 传感器数据更新 |
| `diagnosis_update` | 诊断结果更新 |
| `alarm_new` | 新告警 |

```javascript
// 使用方式
import { connect, on, send } from '@/utils/websocket';

connect();
on('device_online', (data) => { console.log('设备上线:', data); });
send({ type: 'ping' });
```

### 2.3 后端交互工具 (`backend.js`)

**文件路径**：`src/utils/backend.js`

| 函数 | 签名 | 说明 |
|------|------|------|
| `getBaseUrl` | `getBaseUrl() -> string` | 获取后端基础 URL |
| `buildUrl` | `buildUrl(path: string, params?: object) -> string` | 构建完整 URL（带查询参数） |
| `getApiBaseURL` | `getApiBaseURL() -> string` | 获取 API 基础 URL（优先使用配置/存储的值，其次自动判断同源，最后回退到默认地址） |
| `getWebSocketURL` | `getWebSocketURL(path?: string) -> string` | 获取 WebSocket 完整 URL（自动拼接 `ws://`/`wss://` 协议和 Token 查询参数） |

### 2.4 常量定义 (`constants.js`)

**文件路径**：`src/utils/constants.js`

| 常量 | 类型 | 说明 |
|------|------|------|
| `DEVICE_STATUS_MAP` | `object` | 设备状态映射（normal/warning/critical → 中文） |
| `FAULT_TYPE_MAP` | `object` | 故障类型映射 |
| `ALARM_LEVEL_MAP` | `object` | 告警级别映射 |
| `DENOISE_METHODS` | `Array` | 可用去噪方法列表 |
| `BEARING_METHODS` | `Array` | 可用轴承分析方法列表 |
| `GEAR_METHODS` | `Array` | 可用齿轮分析方法列表 |
| `HEALTH_THRESHOLD_WARNING` | `number` | `60` — 健康度预警阈值 |
| `HEALTH_THRESHOLD_NORMAL` | `number` | `80` — 健康度正常阈值 |
| `DEFAULT_SAMPLE_RATE` | `number` | `25600` — 默认采样率 Hz |
| `DEFAULT_DURATION` | `number` | `10` — 默认采集时长秒 |
| `COLORS` | `object` | Element Plus 主题色常量 `{primary, success, warning, danger, info}` |
| `DEFAULT_CHANNEL_NAMES` | `object` | 默认通道名称映射 `{1: '通道1-轴承附近', 2: '通道2-驱动端', 3: '通道3-风扇端'}` |

### 2.5 格式化工具 (`format.js`)

**文件路径**：`src/utils/format.js`

| 函数 | 签名 | 说明 |
|------|------|------|
| `formatDateTime` | `formatDateTime(dt: string \| Date) -> string` | 格式化完整日期时间（`YYYY-MM-DD HH:mm:ss`） |
| `formatTime` | `formatTime(dt: string \| Date) -> string` | 格式化短日期时间（`MM-DD HH:mm`） |
| `formatNumber` | `formatNumber(num: number, decimals: number = 2) -> string` | 格式化数字 |
| `formatPercent` | `formatPercent(value: number, digits: number = 0) -> string` | 格式化为百分比（如 `85%`） |
| `formatHealthScore` | `formatHealthScore(score: number) -> string` | 格式化健康度（带状态颜色） |
| `formatFileSize` | `formatFileSize(bytes: number) -> string` | 格式化文件大小 |

### 2.6 数学计算工具 (`math.js`)

**文件路径**：`src/utils/math.js`

| 函数 | 签名 | 说明 |
|------|------|------|
| `linearInterpolate` | `linearInterpolate(x: number, x0: number, x1: number, y0: number, y1: number) -> number` | 线性插值 |
| `clamp` | `clamp(value: number, min: number, max: number) -> number` | 限制值范围 |
| `calcRms` | `calcRms(arr: number[]) -> number` | 计算数组 RMS 均方根值 |
| `calcPeak` | `calcPeak(arr: number[]) -> number` | 计算数组峰值（最大绝对值） |

### 2.7 状态处理工具 (`status.js`)

**文件路径**：`src/utils/status.js`

| 函数 | 签名 | 说明 |
|------|------|------|
| `getDeviceStatusText` | `getDeviceStatusText(status: string) -> string` | 获取设备状态文本 |
| `getDeviceStatusColor` | `getDeviceStatusColor(status: string) -> string` | 获取设备状态颜色 |
| `getAlarmLevelColor` | `getAlarmLevelColor(level: string) -> string` | 获取告警级别颜色 |
| `getStatusType` | `getStatusType(status: string) -> string` | 获取状态 Element Plus 标签类型（`success`/`warning`/`danger`/`info`） |
| `getStatusText` | `getStatusText(status: string) -> string` | 获取状态中文文本（正常/预警/故障/离线/未知） |
| `getStatusColor` | `getStatusColor(status: string) -> string` | 获取状态十六进制颜色 |
| `getHealthLevel` | `getHealthLevel(score: number) -> string` | 根据健康度分数返回级别（`normal`/`warning`/`fault`/`unknown`） |
| `getHealthColor` | `getHealthColor(score: number) -> string` | 根据健康度分数返回十六进制颜色 |

---

## 3. 通用组件 (Components)

### 3.1 Layout.vue

**文件路径**：`src/components/Layout.vue`

| 属性 | 类型 | 说明 |
|------|------|------|
| **用途** | — | 系统整体布局（侧边导航、顶部栏、内容区） |

**关键方法**：

| 方法 | 说明 |
|------|------|
| `handleMenuSelect(index)` | 菜单选中切换路由 |
| `handleLogout()` | 退出登录 |

---

### 3.2 DiagnosisDetail.vue

**文件路径**：`src/components/DiagnosisDetail.vue`

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `orderAnalysis` | `object \| null` | `null` | 阶次/包络/频谱分析明细 |
| `rotFreq` | `number \| null` | `null` | 估计转频（Hz） |
| `rotRpm` | `number \| null` | `null` | 估计转速（RPM） |

**用途**：诊断结果明细展示（健康度、故障概率、阶次分析）

---

### 3.3 VibrationChart.vue

**文件路径**：`src/components/charts/VibrationChart.vue`

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `option` | `object` | `{}` | ECharts 配置项 |
| `height` | `string \| number` | `'300px'` | 图表高度 |

**用途**：ECharts 振动数据图表封装

---

### 3.4 DetailHeader.vue

**文件路径**：`src/components/dataview/DetailHeader.vue`

| Props | 类型 | 默认值 | 说明 |
|-------|------|--------|------|
| `devices` | `Array` | `[]` | 设备列表 |
| `selectedDevice` | `string` | `''` | 当前设备 ID |
| `batches` | `Array` | `[]` | 批次列表 |
| `selectedBatch` | `number` | `null` | 当前批次号 |
| `channels` | `Array` | `[]` | 通道列表 |
| `selectedChannel` | `number` | `1` | 当前通道号 |
| `loading` | `boolean` | `false` | 加载状态 |
| `denoiseMethod` | `string` | `'none'` | 去噪方法 |

| Emits | 说明 |
|-------|------|
| `update:selectedDevice` | 设备切换 |
| `update:selectedBatch` | 批次切换 |
| `update:selectedChannel` | 通道切换 |
| `update:denoiseMethod` | 去噪方法切换 |
| `reanalyze` | 重新诊断 |
| `reanalyzeAll` | 全部重新诊断 |
| `deleteBatch` | 删除批次 |
| `exportCsv` | 导出 CSV |

**用途**：数据详情页头部工具栏

---

### 3.5 DeviceTable.vue

**文件路径**：`src/components/dataview/DeviceTable.vue`

| Props | 类型 | 默认值 | 说明 |
|-------|------|--------|------|
| `data` | `Array` | `[]` | 表格数据（批次列表） |
| `loading` | `boolean` | `false` | 加载状态 |

| Emits | 说明 |
|-------|------|
| `rowClick` | 点击行 |
| `batchSelect` | 选中批次 |

**用途**：设备批次数据表格

---

### 3.6 DiagnosisAlert.vue

**文件路径**：`src/components/dataview/DiagnosisAlert.vue`

| Props | 类型 | 默认值 | 说明 |
|-------|------|--------|------|
| `diagnosis` | `object \| null` | `null` | 诊断结果对象 |
| `healthScore` | `number` | `100` | 健康度分数 |

**用途**：诊断告警提示组件（根据健康度显示不同级别警告）

---

### 3.7 TimeDomainPanel.vue

**文件路径**：`src/components/dataview/TimeDomainPanel.vue`

| Props | 类型 | 默认值 | 说明 |
|-------|------|--------|------|
| `timeData` | `Array` | `[]` | 时域数据点数组 |
| `sampleRate` | `number` | `25600` | 采样率 |
| `channelName` | `string` | `''` | 通道名称 |

**用途**：时域波形展示面板

---

## 4. 路由配置

**文件路径**：`src/router/index.js`

| 路由路径 | 组件 | 说明 |
|---------|------|------|
| `/login` | `Login.vue` | 登录页 |
| `/` | `Layout.vue` | 布局容器 |
| `/dashboard` | `Dashboard.vue` | 总览页 |
| `/monitor` | `Monitor.vue` | 监测页 |
| `/data` | `DataView.vue` | 数据查看页 |
| `/research` | `ResearchDiagnosis.vue` | 研究诊断页 |
| `/alarm` | `Alarm.vue` | 告警页 |
| `/settings` | `Settings.vue` | 设置页 |
| `/logs` | `Logs.vue` | 日志页 |

**导航守卫**：

| 守卫 | 说明 |
|------|------|
| `beforeEach` | 检查 Token，未登录跳转 `/login` |

---

*文档生成时间：2026-05-17*
*维护者：AI Agent（修改前端代码时请务必同步更新）*
