/**
 * 前端全局常量
 */

// 健康度阈值
export const HEALTH_THRESHOLD_WARNING = 60
export const HEALTH_THRESHOLD_NORMAL = 80

// 默认采样率
export const DEFAULT_SAMPLE_RATE = 25600
export const DEFAULT_DURATION = 10

export const ACQUISITION_STATUS_POLL_MS = 2000

// 颜色常量（与 styles/variables.css 设计令牌一致，供 JS/图表场景使用）
export const COLORS = {
  primary: '#4F46E5',
  success: '#10B981',
  warning: '#F59E0B',
  danger: '#EF4444',
  info: '#64748B',
}

// 通道默认名称
export const DEFAULT_CHANNEL_NAMES = {
  1: '通道1-轴承附近',
  2: '通道2-驱动端',
  3: '通道3-风扇端',
}
