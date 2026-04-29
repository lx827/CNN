# 风机齿轮箱智能故障诊断系统

## 📋 项目简介

这是一个基于 Vue3 + Vite + Element Plus + ECharts 的风机齿轮箱智能故障诊断系统前端项目，用于机械故障诊断大创项目的演示。

## 🛠️ 技术栈

- **Vue 3** - 前端框架
- **Vite** - 构建工具
- **Element Plus** - UI 组件库
- **ECharts** - 图表可视化
- **Axios** - HTTP 请求库
- **Vue Router** - 路由管理

## 📁 项目结构

```
wind-turbine-diagnosis/
├── index.html                    # 入口 HTML
├── package.json                  # 项目依赖配置
├── vite.config.js                # Vite 配置文件
├── src/
│   ├── main.js                   # 应用入口
│   ├── App.vue                   # 根组件
│   ├── api/
│   │   └── index.js              # API 接口封装（模拟数据）
│   ├── components/
│   │   └── Layout.vue            # 主布局组件（导航栏）
│   ├── router/
│   │   └── index.js              # 路由配置
│   ├── utils/
│   │   └── request.js            # Axios 请求工具类
│   └── views/
│       ├── Dashboard.vue         # 首页-设备总览
│       ├── Monitor.vue           # 实时监测页
│       ├── Diagnosis.vue         # 故障诊断页
│       └── Alarm.vue             # 告警记录页
```

## 🚀 安装与运行

### 前置要求

- **Node.js** >= 16.0.0（推荐 18+）
- **npm** >= 8.0.0

### 安装步骤

```bash
# 1. 进入项目目录
cd wind-turbine-diagnosis

# 2. 安装依赖
npm install

# 3. 启动开发服务器
npm run dev
```

启动后浏览器会自动打开 `http://localhost:3000`

### 其他命令

```bash
# 构建生产版本
npm run build

# 预览生产构建
npm run preview
```

## 📄 功能页面

### 1. 设备总览 (Dashboard)
- 设备状态卡片（状态、健康度、运行时长、告警数）
- 健康度仪表盘（ECharts  Gauge 图）
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

## 🔌 接口说明

所有接口都在 `src/api/index.js` 中，目前使用模拟数据：

| 接口名 | 说明 | 返回数据 |
|--------|------|----------|
| `getDeviceInfo()` | 获取设备信息 | 设备状态、健康度、部件列表 |
| `getRealtimeVibrationData()` | 获取实时振动数据 | 多通道波形数据、运行参数 |
| `getFaultDiagnosisResult()` | 获取故障诊断结果 | 故障列表、IMF分量、概率分布 |
| `getHistoryAlarmList()` | 获取历史告警记录 | 告警列表、总数 |
| `getStatistics()` | 获取统计数据 | 故障分布、月度趋势 |

## 🔄 如何对接真实后端

### 步骤 1：修改 baseURL

打开 `src/utils/request.js`，修改 `baseURL`：

```javascript
const request = axios.create({
  baseURL: 'http://your-api-domain.com/api',  // 改成真实后端地址
  timeout: 5000
})
```

### 步骤 2：替换模拟接口

打开 `src/api/index.js`，将所有 `Promise.resolve()` 替换为真实请求：

```javascript
// 修改前（模拟数据）
export const getDeviceInfo = () => {
  return Promise.resolve({
    code: 200,
    data: { ... }
  })
}

// 修改后（真实请求）
export const getDeviceInfo = () => {
  return request.get('/device/info')  // 调用真实接口
}
```

### 步骤 3：处理跨域（如果需要）

如果前后端域名不同，需要在 `vite.config.js` 配置代理：

```javascript
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    open: true,
    proxy: {
      '/api': {
        target: 'http://your-api-domain.com',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
```

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

1. **必须先安装 Node.js**：前往 https://nodejs.org 下载 LTS 版本
2. 如果 npm install 报错，可以尝试：
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
