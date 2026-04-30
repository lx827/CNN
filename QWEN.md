# QWEN.md - 风机齿轮箱智能故障诊断系统

## 项目概览

这是一个基于 **Vue3 + Vite + Element Plus + ECharts** 的前端项目，用于机械故障诊断大创项目的演示。系统展示风机齿轮箱的实时监测、故障诊断和告警管理功能。

## 技术栈

- **Vue 3** — 前端框架
- **Vite** — 构建工具
- **Element Plus** — UI 组件库
- **ECharts** — 图表可视化
- **Axios** — HTTP 请求库
- **Vue Router** — 路由管理

## 构建与运行

```bash
cd wind-turbine-diagnosis

# 安装依赖
npm install

# 开发服务器（http://localhost:3000，自动打开浏览器）
npm run dev

# 生产构建
npm run build

# 预览生产构建
npm run preview
```

**前置要求：** Node.js >= 16.0.0（推荐 18+）

## 项目结构

```
d:\code\CNN\
└── wind-turbine-diagnosis/
    ├── index.html                     # 入口 HTML
    ├── package.json                   # 依赖配置
    ├── vite.config.js                 # Vite 配置（port: 3000）
    └── src/
        ├── main.js                    # 应用入口（注册 Element Plus + 图标）
        ├── App.vue                    # 根组件
        ├── api/index.js               # API 接口封装（调用虚拟数据库）
        ├── components/
        │   └── Layout.vue             # 主布局组件（导航栏）
        ├── database/
        │   └── virtual-db.js          # 虚拟数据库层（模拟数据）
        ├── router/index.js            # 路由配置
        ├── utils/request.js           # Axios 请求工具类
        └── views/
            ├── Dashboard.vue          # 设备总览（健康度仪表盘、故障分布饼图）
            ├── Monitor.vue            # 实时监测（振动波形动态刷新）
            ├── Diagnosis.vue          # 故障诊断（IMF分解、故障概率）
            └── Alarm.vue             # 告警记录（分页列表、详情对话框）
```

## 功能页面

| 页面 | 功能 |
|------|------|
| **Dashboard** | 设备状态卡片、健康度仪表盘（Gauge图）、故障类型分布饼图、部件状态表格 |
| **Monitor** | 传感器状态指示灯、运行参数、振动信号时域/频域动态波形图、暂停/开始控制 |
| **Diagnosis** | 诊断结果概要、故障详情、IMF分解能量分布柱状图、故障概率横向柱状图 |
| **Alarm** | 告警统计卡片、告警记录列表（分页）、详情查看对话框 |

## 数据架构

项目使用 **虚拟数据库层** (`src/database/virtual-db.js`) 模拟数据库操作，不依赖后端即可运行演示。

```
Vue 页面 → src/api/index.js → src/database/virtual-db.js → 虚拟数据表（内存）
```

后期可通过修改 `virtual-db.js` 或 `api/index.js` 对接真实数据库或后端 API。

## 开发约定

- **主色调：** 深蓝色 `#165DFF`
- **状态色：** 🟢 正常 `#52C41A` / 🟡 预警 `#FAAD14` / 🔴 故障 `#F5222D`
- **风格：** 工业科技风，简洁清晰
- **模拟数据：** 设备健康度 87 分，6 个部件（2 个预警），3 个振动通道，28 条告警记录
