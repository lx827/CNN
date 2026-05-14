# 风机齿轮箱智能故障诊断系统

## 📋 项目简介

这是一个基于 **Vue3 + Vite + Element Plus + ECharts** 的风机齿轮箱智能故障诊断系统前端项目，用于机械故障诊断大创项目的演示。

系统包含设备总览、实时监测、数据查看、故障诊断、告警记录五大功能模块，对接真实 FastAPI 后端，支持振动信号的实时频谱计算与故障诊断分析。

## 🛠️ 技术栈

- **Vue 3** — 前端框架
- **Vite** — 构建工具
- **Element Plus** — UI 组件库
- **ECharts** — 图表可视化
- **Axios** — HTTP 请求库
- **Vue Router** — 路由管理（Hash 模式，支持离线访问）
- **vite-plugin-singlefile** — 将构建产物打包为单个 HTML 文件

## 📁 项目结构

```
wind-turbine-diagnosis/
├── index.html                    # 入口 HTML
├── package.json                  # 项目依赖配置
├── vite.config.js                # Vite 配置（代理到后端）
├── src/
│   ├── main.js                   # 应用入口
│   ├── App.vue                   # 根组件
│   ├── api/
│   │   ├── index.js              # 通用 API 接口封装
│   │   └── data.js               # DataView 页面 API（频谱/诊断）
│   ├── components/
│   │   └── Layout.vue            # 主布局组件（侧边导航栏）
│   ├── router/
│   │   └── index.js              # 路由配置（createWebHashHistory）
│   ├── utils/
│   │   └── request.js            # Axios 请求工具类
│   └── views/
│       ├── Dashboard.vue         # 设备总览
│       ├── Monitor.vue           # 实时监测
│       ├── DataView.vue          # 数据查看（频谱/诊断分析）
│       ├── Diagnosis.vue         # 故障诊断
│       ├── Alarm.vue             # 告警记录
│       ├── Settings.vue          # 系统设置
│       └── Logs.vue              # 系统日志
```

## 🚀 安装与运行

### 前置要求

- **Node.js** >= 16.0.0（推荐 18+）
- **npm** >= 8.0.0

### 开发模式

```bash
# 1. 进入项目目录
cd wind-turbine-diagnosis

# 2. 安装依赖
npm install

# 3. 启动开发服务器
npm run dev
```

启动后浏览器自动打开 `http://localhost:3000`

### 其他命令

```bash
# 构建生产版本
npm run build

# 预览生产构建
npm run preview
```

## 📦 离线分发（发给别人直接打开）

项目已配置 `vite-plugin-singlefile`，构建时会将所有 JS/CSS 内联到单个 HTML 文件中，**无需前端服务器，双击即可打开**。

```bash
# 构建单文件版本
npm run build
```

构建完成后，将 `dist/index.html` 单独复制出来发给对方即可。对方无需安装 Node.js，直接用浏览器打开该文件即可使用；API 默认连接 `http://8.137.96.104:8000`，也可在控制台执行 `localStorage.setItem('backend_base_url', 'http://你的后端地址:8000')` 指定后端。

> **原理说明：**
>
> - 路由使用 `createWebHashHistory`（`#` 哈希路由），兼容 `file://` 协议
> - `vite-plugin-singlefile` 将所有资源内联，避免 `file://` 下的静态资源限制
> - `file://` 与 `vite preview` 场景没有 Vite 代理，前端会自动使用后端基地址配置

## 📄 功能页面

### 1. 设备总览 (Dashboard)

- 设备状态卡片（状态、健康度、运行时长、告警数）
- 健康度仪表盘（ECharts Gauge 图）
- 故障类型分布饼图
- 部件状态详情表格

### 2. 实时监测 (Monitor)

- 传感器状态指示灯
- 设备运行参数（转速、温度、负载）
- 振动信号时域波形图（动态刷新）
- 频域谱图（动态刷新）
- 支持暂停/开始监测

### 3. 数据查看 (DataView)

- 设备批次列表（普通/特殊数据）
- 原始时域波形图
- 按需计算的频谱分析：FFT、STFT、包络谱、阶次谱、倒谱
- 统计指标（含滑窗统计）
- 齿轮诊断分析
- **全算法综合诊断**：支持多种轴承/齿轮方法对比，结果按去噪方法缓存
- CSV 数据导出

### 4. 故障诊断 (Diagnosis)

- 诊断结果概要
- 故障详情（部件、类型、置信度、严重程度）
- IMF 分解能量分布图（柱状图）
- 故障概率分布图（横向柱状图）

### 5. 告警记录 (Alarm)

- 告警统计卡片（严重/预警/已处理）
- 告警记录列表（分页）
- 详情查看对话框

## 🔌 数据层说明

### 当前架构：前端 → FastAPI 后端 → SQLite/MySQL

项目已对接真实后端服务，所有数据通过 HTTP API 从后端获取：

- ✅ 设备信息、批次数据、振动信号实时查询
- ✅ FFT / STFT / 包络 / 阶次 / 倒谱 实时计算
- ✅ 轴承/齿轮故障诊断分析
- ✅ 诊断结果按去噪方法分版本缓存

### 数据流

```
Vue 页面 → src/api/*.js → Axios → FastAPI 后端 → SQLite/MySQL
```

### 后端 API 模块

| 模块 | 说明 |
|------|------|
| `auth` | JWT 登录认证 |
| `dashboard` | 设备总览统计 |
| `data_view` | 振动数据查询、频谱计算、诊断分析 |
| `diagnosis` | 诊断结果查询 |
| `alarms` | 告警管理 |
| `devices` | 设备 CRUD 与配置 |
| `ingest` | 边端数据接入 |
| `collect` | 采集任务下发 |

### 代理配置

开发模式下，`vite.config.js` 将 `/api` 和 `/ws` 代理到后端服务器：

```javascript
proxy: {
  '/api': { target: 'http://8.137.96.104:8000', changeOrigin: true },
  '/ws':  { target: 'ws://8.137.96.104:8000',  ws: true, changeOrigin: true }
}
```

生产环境由 Nginx 反向代理。`file://` 或 `vite preview` 无法使用开发代理，会自动连接后端基地址；可通过 `window.__BACKEND_BASE_URL__`、`VITE_BACKEND_BASE_URL` 或 `localStorage.backend_base_url` 覆盖。

## 🎨 界面风格

- **主色调**：深蓝色 `#165DFF`
- **状态色**：
  - 🟢 正常：`#52C41A`
  - 🟡 预警：`#FAAD14`
  - 🔴 故障：`#F5222D`
- **风格**：工业科技风，简洁清晰

## 📊 数据来源

系统使用真实轴承数据集（HUSTbear）进行故障诊断演示：

- **数据集路径**：`D:\code\wavelet_study\dataset\HUSTbear\down8192`
- **采样率**：8192 Hz
- **文件格式**：`.npy`（NumPy 一维数组）
- **故障类型**：健康(N)、球故障(B)、内圈故障(IR)、外圈故障(OR)、复合故障(C)
- **转速模式**：恒定转速(CS)、变速(VS)

## ⚠️ 注意事项

1. **必须先安装 Node.js**：前往 <https://nodejs.org> 下载 LTS 版本
2. 启动开发服务器前，确保后端服务已运行：

   ```bash
   cd ../cloud
   . venv/Scripts/activate
   python -m app.main
   ```

3. 如果 `npm install` 报错，可以尝试：

   ```bash
   npm install --legacy-peer-deps
   ```

4. 如果端口 3000 被占用，修改 `vite.config.js` 中的 `port` 配置
5. 生产构建前确保代理地址正确（`vite.config.js` 中的 `target`）

## 📝 答辩演示建议

1. **首页**：展示设备整体状态，突出健康度仪表盘和故障分布图
2. **实时监测**：展示动态刷新的振动波形，说明数据采集频率
3. **数据查看**：
   - 展示 FFT / STFT 频谱分析，说明实时计算能力
   - 展示包络谱和阶次跟踪，体现轴承/齿轮故障诊断方法
   - 演示全算法综合诊断，对比不同诊断方法的检出结果
   - 说明诊断缓存机制：切换去噪方法时自动加载对应缓存
4. **故障诊断**：重点讲解 IMF 分解和故障概率，体现算法逻辑
5. **告警记录**：展示历史数据分析能力，说明系统实用性

## 👨‍💻 开发者

风机齿轮箱智能故障诊断系统 - 机械故障诊断大创项目

---

**祝你答辩顺利！** 🎉
