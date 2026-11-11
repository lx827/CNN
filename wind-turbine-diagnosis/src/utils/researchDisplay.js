/** 研究结果纯展示格式；无需加载请求客户端，空值不转换成0。 */
export const fmt = value => {
  if (value == null) return '-'
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(4) : '-'
}
export const percent = value => {
  if (value == null) return '-'
  const number = Number(value)
  return Number.isFinite(number) ? `${(number * 100).toFixed(1)}%` : '-'
}
export const evaluationStatusType = state => state === 'evaluated' ? 'success' : 'info'
export const evaluationStatusText = state => ({
  evaluated: '已评估', indeterminate: '不可判定', not_evaluable: '不可评估',
})[state] || '不可判定'

export const rawIndicatorView = indicator => {
  if (!indicator || indicator.evaluable === false || indicator.status === 'not_evaluable') return { type: 'info', text: '不可评估' }
  if (indicator.critical) return { type: 'warning', text: '严重超阈值' }
  if (indicator.warning || indicator.significant) return { type: 'warning', text: '显著' }
  if (indicator.significant === false || indicator.warning === false || indicator.critical === false) return { type: 'info', text: '未显著' }
  return { type: 'info', text: '原始读数' }
}
