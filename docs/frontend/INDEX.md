# 前端代码目录索引

> **文档用途**：按文件模块结构组织前端代码，方便 AI Agent 快速定位代码位置和了解各模块职责。
> **维护要求**：新增、重命名或删除文件时，必须同步更新本文档。

---

## 目录

1. [应用入口](#1-应用入口)
2. [API 接口层](#2-api-接口层)
3. [页面组件 (Views)](#3-页面组件-views)
4. [通用组件 (Components)](#4-通用组件-components)
5. [状态管理 (Stores)](#5-状态管理-stores)
6. [路由配置](#6-路由配置)
7. [工具函数 (Utils)](#7-工具函数-utils)
8. [样式文件](#8-样式文件)

---

## 1. 应用入口

| 文件 | 路径 | 职责 |
|------|------|------|
| `main.js` | `wind-turbine-diagnosis/src/main.js` | Vue 应用初始化、路由/状态/Pinia 注册 |
| `App.vue` | `wind-turbine-diagnosis/src/App.vue` | 根组件、路由出口 |

---

## 2. API 接口层

> 所有 API 函数位于 `wind-turbine-diagnosis/src/api/` 目录下，统一通过 `request` 实例发起请求。

| 文件 | 路径 | 职责 | 主要函数 |
|------|------|------|----------|
| `index.js` | `src/api/index.js` | 认证与监控 API 聚合 | `login()`, `getDeviceInfo()`, `getRealtimeVibrationData()` |
| `data.js` | `src/api/data.js` | 数据查看与诊断 API | `getDeviceBatches()`, `getChannelFFT()`, `getChannelFullAnalysis()`, `reanalyzeBatch()` 等 |
| `device.js` | `src/api/device.js` | 设备配置 API | `getDevices()`, `getDeviceConfig()`, `updateDeviceConfig()`, `getAlarmThresholds()` 等 |
| `alarm.js` | `src/api/alarm.js` | 告警管理 API | `getHistoryAlarmList()`, `updateAlarmStatus()`, `deleteAlarm()` |
| `system.js` | `src/api/system.js` | 系统与采集 API | `getSystemLogs()`, `requestCollection()`, `getTaskStatus()` |
| `ingest.js` | `src/api/ingest.js` | 数据接入 API | （边端相关） |

---

## 3. 页面组件 (Views)

> 所有页面组件位于 `wind-turbine-diagnosis/src/views/` 目录下，通过 Vue Router 路由切换。

| 文件 | 路径 | 职责 |
|------|------|------|
| `Login.vue` | `src/views/Login.vue` | 系统登录页 |
| `Dashboard.vue` | `src/views/Dashboard.vue` | 设备总览面板（健康度仪表盘、告警统计） |
| `Monitor.vue` | `src/views/Monitor.vue` | 实时振动监控页（手动采集、实时波形） |
| `DataView.vue` | `src/views/DataView.vue` | **核心数据分析页**（时域/频域/时频/包络/阶次/倒谱/齿轮/全分析） |
| `ResearchDiagnosis.vue` | `src/views/ResearchDiagnosis.vue` | 研究级诊断页（单方法/多方法集成分析） |
| `Alarm.vue` | `src/views/Alarm.vue` | 告警历史列表（筛选、处理、删除） |
| `Settings.vue` | `src/views/Settings.vue` | 系统设置页（设备配置、机械参数、告警阈值） |
| `Logs.vue` | `src/views/Logs.vue` | 系统日志实时查看页 |

---

## 4. 通用组件 (Components)

> 通用组件位于 `wind-turbine-diagnosis/src/components/` 目录下，供多个页面复用。

### 4.1 根级组件

| 文件 | 路径 | 职责 |
|------|------|------|
| `Layout.vue` | `src/components/Layout.vue` | 系统整体布局（侧边导航、顶部栏、内容区插槽） |
| `DiagnosisDetail.vue` | `src/components/DiagnosisDetail.vue` | 诊断结果明细展示（阶次分析、健康度、故障概率） |

### 4.2 图表组件 (charts/)

| 文件 | 路径 | 职责 |
|------|------|------|
| `VibrationChart.vue` | `src/components/charts/VibrationChart.vue` | ECharts 振动数据图表封装 |

### 4.3 数据视图子组件 (dataview/)

| 文件 | 路径 | 职责 |
|------|------|------|
| `DetailHeader.vue` | `src/components/dataview/DetailHeader.vue` | 数据详情页头部工具栏（设备/批次/通道选择器、操作按钮） |
| `DeviceTable.vue` | `src/components/dataview/DeviceTable.vue` | 设备批次数据表格 |
| `DiagnosisAlert.vue` | `src/components/dataview/DiagnosisAlert.vue` | 诊断告警提示组件 |
| `TimeDomainPanel.vue` | `src/components/dataview/TimeDomainPanel.vue` | 时域波形展示面板 |

---

## 5. 状态管理 (Stores)

> 使用 Pinia 进行状态管理，所有 Store 位于 `wind-turbine-diagnosis/src/stores/` 目录下。

| 文件 | 路径 | 职责 | 主要 State/Actions |
|------|------|------|-------------------|
| `index.js` | `src/stores/index.js` | Store 统一导出 | — |
| `userStore.js` | `src/stores/userStore.js` | 用户状态管理 | `token`, `isLoggedIn`, `login()`, `logout()` |
| `deviceStore.js` | `src/stores/deviceStore.js` | 设备状态管理 | `devices`, `selectedDevice`, `setDevices()`, `selectDevice()` |

---

## 6. 路由配置

| 文件 | 路径 | 职责 |
|------|------|------|
| `index.js` | `src/router/index.js` | Vue Router 路由定义、导航守卫 |

---

## 7. 工具函数 (Utils)

| 文件 | 路径 | 职责 |
|------|------|------|
| `request.js` | `src/utils/request.js` | Axios 请求封装（Token 注入、响应拦截、错误处理） |
| `websocket.js` | `src/utils/websocket.js` | WebSocket 连接管理、事件订阅 |
| `backend.js` | `src/utils/backend.js` | 后端交互辅助工具 |
| `constants.js` | `src/utils/constants.js` | 全局常量定义（故障类型映射、状态枚举等） |
| `format.js` | `src/utils/format.js` | 数据格式化工具（时间/数字/单位转换） |
| `math.js` | `src/utils/math.js` | 数学计算工具 |
| `status.js` | `src/utils/status.js` | 状态处理工具（设备在线/离线状态判断） |

---

## 8. 样式文件

| 文件 | 路径 | 职责 |
|------|------|------|
| `variables.css` | `src/styles/variables.css` | CSS 变量定义（主题色、间距、字体等） |

---

## 文件统计

| 类别 | 数量 |
|------|------|
| Vue 组件 | 16 个 |
| JavaScript 模块 | 18 个 |
| CSS 样式 | 1 个 |
| **总计** | **35 个文件** |

---

*文档生成时间：2026-05-17*
*维护者：AI Agent（修改代码结构时请务必同步更新）*
