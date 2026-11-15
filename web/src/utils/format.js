/**
 * 通用格式化工具函数
 */

export function formatDateTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  }).replace(/\//g, '-')
}

export function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  }).replace(/\//g, '-')
}

export function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || isNaN(value)) return '-'
  return Number(value).toFixed(digits)
}

export function formatPercent(value, digits = 0) {
  if (value === null || value === undefined || isNaN(value)) return '-'
  return (Number(value) * 100).toFixed(digits) + '%'
}
