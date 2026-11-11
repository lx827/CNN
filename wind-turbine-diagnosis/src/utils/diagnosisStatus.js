/**
 * 诊断综合结论的唯一前端展示映射。
 * evaluation_status 是指标评估状态，不在此与诊断结论混用。
 */
const STATUS_VIEWS = new Map([
  ['normal', { text: '正常', tone: 'success', tagType: 'success', alertType: 'success' }],
  ['warning', { text: '预警', tone: 'warning', tagType: 'warning', alertType: 'warning' }],
  ['fault', { text: '故障', tone: 'danger', tagType: 'danger', alertType: 'error' }],
  ['critical', { text: '故障', tone: 'danger', tagType: 'danger', alertType: 'error' }],
  ['indeterminate', { text: '不可判定', tone: 'info', tagType: 'info', alertType: 'info' }],
  ['not_evaluable', { text: '不可评估', tone: 'info', tagType: 'info', alertType: 'info' }],
])

const UNKNOWN_VIEW = { text: '未知', tone: 'info', tagType: 'info', alertType: 'info' }

export function getDiagnosisStatusView(status) {
  return { ...(STATUS_VIEWS.get(status) || UNKNOWN_VIEW) }
}
