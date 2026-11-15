/**
 * ECharts 全局图表主题 —— 与 styles/variables.css 令牌保持一致
 * 所有图表 option 以此为基底，禁止在业务代码里散落配色与坐标轴样式。
 */
import { COLORS } from './constants.js'

/** 分类系列色板（按取色顺序） */
export const CHART_PALETTE = [
  COLORS.primary,   // 靛蓝
  '#0ea5e9',        // 天蓝
  '#10b981',        // 翠绿
  '#f59e0b',        // 琥珀
  '#8b5cf6',        // 紫
  '#ec4899',        // 品红
  '#14b8a6',        // 青
  '#ef4444',        // 红
]

/** 与 variables.css 令牌对应的文本/边框色（JS 图表场景使用） */
export const TEXT_PRIMARY = '#1e293b'
export const TEXT_REGULAR = '#475569'
export const TEXT_SECONDARY = '#94a3b8'
export const BORDER_LIGHT = '#eef1f7'
export const BORDER = '#e2e8f0'

/** 坐标轴通用样式（直角坐标系） */
export const AXIS_STYLE = {
  axisLine: { lineStyle: { color: BORDER } },
  axisTick: { show: false },
  axisLabel: { color: TEXT_SECONDARY, fontSize: 11 },
  splitLine: { lineStyle: { color: BORDER_LIGHT, type: 'dashed' } },
}

/** 提示框通用样式 */
export const TOOLTIP_STYLE = {
  backgroundColor: '#ffffff',
  borderColor: BORDER_LIGHT,
  borderWidth: 1,
  textStyle: { color: TEXT_PRIMARY, fontSize: 12 },
  extraCssText: 'box-shadow: 0 4px 12px -2px rgba(15,23,42,0.12); border-radius: 8px; padding: 8px 12px;',
}

/**
 * 直角坐标系图表基底 option。
 * 用法：echarts.setOption({ ...baseCartesianOption(), xAxis: {...}, series: [...] })
 */
export function baseCartesianOption() {
  return {
    color: CHART_PALETTE,
    textStyle: { fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif" },
    grid: { left: 48, right: 24, top: 32, bottom: 32, containLabel: false },
    tooltip: { trigger: 'axis', ...TOOLTIP_STYLE },
    animationDuration: 400,
    animationEasing: 'cubicOut',
  }
}

/** 饼图/仪表盘等无坐标轴图表的基底 */
export function baseOption() {
  return {
    color: CHART_PALETTE,
    textStyle: { fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif" },
    tooltip: { ...TOOLTIP_STYLE },
    animationDuration: 400,
  }
}

/** 空数据占位标题 */
export function emptyTitle(text) {
  return {
    show: true,
    text,
    left: 'center',
    top: 'center',
    textStyle: { color: TEXT_SECONDARY, fontSize: 14, fontWeight: 400 },
  }
}
