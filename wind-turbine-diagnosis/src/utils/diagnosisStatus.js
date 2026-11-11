/**
 * 唯一诊断领域展示 adapter。输入完整两维结果；不接受旧 status 字符串。
 * 连接在线状态与算法表示状态独立于诊断结论。
 */
const views = {
  normal: { color: '#52C41A', label: '正常', tone: 'success', icon: 'CircleCheck', tagType: 'success', alertType: 'success' },
  warning: { color: '#FAAD14', label: '预警', tone: 'warning', icon: 'Warning', tagType: 'warning', alertType: 'warning' },
  fault: { color: '#F5222D', label: '故障', tone: 'danger', icon: 'CircleClose', tagType: 'danger', alertType: 'error' },
}
const unknown = { color: '#909399', label: '未知', tone: 'info', icon: 'QuestionFilled', tagType: 'info', alertType: 'info' }

export function getDiagnosisView(result) {
  if (!result || typeof result !== 'object') return { ...unknown, scoreText: '-', text: unknown.label }
  const state = result.evaluation_status
  const conclusion = result.diagnosis_conclusion
  const score = result.health_score
  let view = unknown
  const validScore = typeof score === 'number' && Number.isFinite(score) && score >= 0 && score <= 100
  const localEvaluation = result.object_id != null && !Object.hasOwn(result, 'health_score')
  if (state === 'evaluated' && Object.hasOwn(views, conclusion) && (validScore || localEvaluation)) {
    view = views[conclusion]
  } else if ((state === 'indeterminate' || state === 'not_evaluable') && conclusion === 'unknown' && (score === null || localEvaluation)) {
    view = { ...unknown, label: state === 'indeterminate' ? '不可判定' : '不可评估' }
  }
  return { ...view, text: view.label, scoreText: view === unknown || state !== 'evaluated' || !validScore ? '-' : score.toFixed(1) }
}
