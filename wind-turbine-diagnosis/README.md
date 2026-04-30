# 风机齿轮箱智能故障诊断系统

## 📋 项目简介

这是一个基于 **Vue3 + Vite + Element Plus + ECharts** 的风机齿轮箱智能故障诊断系统前端项目，用于机械故障诊断大创项目的演示。

系统包含设备总览、实时监测、故障诊断、告警记录四大功能模块，使用虚拟数据库层模拟数据，无需后端即可完整运行。

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
├── vite.config.js                # Vite 配置（含 singlefile 插件）
├── src/
│   ├── main.js                   # 应用入口
│   ├── App.vue                   # 根组件
│   ├── api/
│   │   └── index.js              # API 接口封装（调用虚拟数据库）
│   ├── components/
│   │   └── Layout.vue            # 主布局组件（侧边导航栏）
│   ├── database/
│   │   └── virtual-db.js         # 虚拟数据库层（模拟数据）
│   ├── router/
│   │   └── index.js              # 路由配置（createWebHashHistory）
│   ├── utils/
│   │   └── request.js            # Axios 请求工具类
│   └── views/
│       ├── Dashboard.vue         # 设备总览
│       ├── Monitor.vue           # 实时监测
│       ├── Diagnosis.vue         # 故障诊断
│       └── Alarm.vue             # 告警记录
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

项目已配置 `vite-plugin-singlefile`，构建时会将所有 JS/CSS 内联到单个 HTML 文件中，**无需服务器环境，双击即可打开**。

```bash
# 构建单文件版本
npm run build
```

构建完成后，将 `dist/index.html` 单独复制出来发给对方即可。对方无需安装 Node.js，直接用浏览器打开该文件即可使用全部功能。

> **原理说明：**
>
> - 路由使用 `createWebHashHistory`（`#` 哈希路由），兼容 `file://` 协议
> - `vite-plugin-singlefile` 将所有资源内联，避免 `file://` 下的 CORS 限制

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

### 3. 故障诊断 (Diagnosis)

- 诊断结果概要
- 故障详情（部件、类型、置信度、严重程度）
- IMF 分解能量分布图（柱状图）
- 故障概率分布图（横向柱状图）

### 4. 告警记录 (Alarm)

- 告警统计卡片（严重/预警/已处理）
- 告警记录列表（分页）
- 详情查看对话框

## 🔌 数据层说明

### 当前架构：前端 → 虚拟数据库

项目使用 **虚拟数据库层** (`src/database/virtual-db.js`) 模拟数据库操作：

- ✅ 不依赖后端 HTTP 服务
- ✅ 不依赖真实数据库
- ✅ 直接在前端模拟数据库读写
- ✅ 后期可替换为真实数据库连接

### 数据流

```
Vue 页面 → src/api/index.js → src/database/virtual-db.js → 虚拟数据表（内存）
```

### 虚拟数据表

| 表名 | 说明 |
|------|------|
| `devicesTable` | 设备信息表 |
| `componentsTable` | 部件状态表 |
| `vibrationDataTable` | 振动数据表（实时） |
| `diagnosisResultTable` | 诊断结果表 |
| `alarmRecordsTable` | 告警记录表 |
| `statisticsTable` | 统计表 |

## 🔄 后期对接真实数据库

### 方案 1：保留虚拟数据库，替换数据源

修改 `src/database/virtual-db.js` 中的查询函数，将内存数据替换为真实数据库查询。

### 方案 2：通过后端 API 间接连接

修改 `src/api/index.js` 改为 HTTP 请求，并在 `src/utils/request.js` 中配置 `baseURL`。

## 🎨 界面风格

- **主色调**：深蓝色 `#165DFF`
- **状态色**：
  - 🟢 正常：`#52C41A`
  - 🟡 预警：`#FAAD14`
  - 🔴 故障：`#F5222D`
- **风格**：工业科技风，简洁清晰

## 📊 数据模拟说明

- 设备健康度：87分
- 部件状态：6个（2个预警）
- 振动信号：3个通道，模拟正弦波 + 噪声
- 故障诊断：2个故障（行星齿轮组磨损、轴承剥落）
- 告警记录：28条历史数据

## ⚠️ 注意事项

1. **必须先安装 Node.js**：前往 <https://nodejs.org> 下载 LTS 版本
2. 如果 `npm install` 报错，可以尝试：

   ```bash
   npm install --legacy-peer-deps
   ```

3. 如果端口 3000 被占用，修改 `vite.config.js` 中的 `port` 配置
4. 项目使用模拟数据，无需后端即可运行演示

## 📝 答辩演示建议

1. **首页**：展示设备整体状态，突出健康度仪表盘和故障分布图
2. **实时监测**：展示动态刷新的振动波形，说明数据采集频率
3. **故障诊断**：重点讲解 IMF 分解和故障概率，体现算法逻辑
4. **告警记录**：展示历史数据分析能力，说明系统实用性

## 👨‍💻 开发者

风机齿轮箱智能故障诊断系统 - 机械故障诊断大创项目

---

**祝你答辩顺利！** 🎉
