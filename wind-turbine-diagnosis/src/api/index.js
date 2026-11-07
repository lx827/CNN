/**
 * API 接口层 —— 按域模块汇总出口
 * 负责调用云端 FastAPI 后端服务,并将后端数据转换为前端需要的格式
 *
 * 模块划分(与后端路由一一对应,契约事实源 docs/api/openapi.json):
 *   auth.js        认证(/api/auth)
 *   dashboard.js   设备总览(/api/dashboard)
 *   monitor.js     实时监测(/api/monitor)
 *   data.js        数据查看(/api/data 数据与频谱部分)
 *   diagnosis.js   诊断(/api/data 诊断与分析部分)
 *   devices.js     设备配置(/api/devices)
 *   alarms.js      告警(/api/alarms)
 *   system.js      系统日志与手动采集(/api/logs、/api/collect)
 *   acquisition.js DC24 采集与实时示波(/api/acquisition)
 *   ingest.js      边端数据接入(/api/ingest,前端暂不直接调用)
 *
 * 后端地址通过 vite.config.js 的 proxy 配置代理;视图优先从具体域模块导入,
 * 汇总出口供需要跨域批量导入的场合使用。
 */
export * from './auth'
export * from './dashboard'
export * from './monitor'
export * from './data'
export * from './diagnosis'
export * from './devices'
export * from './alarms'
export * from './system'
export * from './acquisition'
export * from './ingest'
