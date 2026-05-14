/**
 * 设备/诊断状态映射工具
 */

export const STATUS_MAP = {
  normal: { type: 'success', text: '正常', color: '#52C41A' },
  warning: { type: 'warning', text: '预警', color: '#FAAD14' },
  fault: { type: 'danger', text: '故障', color: '#F5222D' },
  offline: { type: 'info', text: '离线', color: '#909399' },
}

export function getStatusType(status) {
  return STATUS_MAP[status]?.type || 'info'
}

export function getStatusText(status) {
  return STATUS_MAP[status]?.text || '未知'
}

export function getStatusColor(status) {
  return STATUS_MAP[status]?.color || '#909399'
}

export function getHealthColor(score) {
  if (score === null || score === undefined) return '#909399'
  if (score >= 80) return '#52C41A'
  if (score >= 60) return '#FAAD14'
  return '#F5222D'
}

export function getHealthLevel(score) {
  if (score === null || score === undefined) return 'unknown'
  if (score >= 80) return 'normal'
  if (score >= 60) return 'warning'
  return 'fault'
}
