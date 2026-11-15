/** 研究组合的专用展示模型。计算态与诊断结论分别展示，空值不变成0。 */
const REASONS = {
  missing_spatial_passage_and_planet_phase_alignment: '缺少传感器通过相位、行星编号或空间对齐记录，无法重组单行星连续信号。',
  insufficient_full_planet_phase_coverage_for_continuous_reassembly: '通过窗口没有覆盖足够完整行星相位，无法连续重组。',
  constant_reference_speed_required: '需要明确提供本段恒定参考轴转频（Hz）。',
  missing_geometry_or_constant_reference_speed: '缺少机械对象或已知恒定参考轴转频。',
  missing_mechanical_geometry: '当前通道缺少完整机械参数。',
  rank_deficient_observations: '观测矩阵秩不足，不能分离指定数量的独立分量。',
  no_VMD_mode_near_mesh_carrier: '没有VMD模态覆盖目标啮合载频。',
  VMD_not_converged: 'VMD尚未收敛，结果仅供近似计算查看。',
  MED_not_converged: 'MED尚未收敛，后续结果仅供近似计算查看。',
  ICA_not_converged: 'ICA尚未收敛，不输出有效分离结果。',
  research_combination_has_no_validated_fault_thresholds: '该组合缺少已验证的故障阈值，不能判断健康或故障。',
  some_multiscale_entropies_are_not_evaluable: '部分尺度无法计算有效能量熵。',
  overlapping_planet_passage_windows: '不同架位行星的通过窗口重叠，无法确认单行星来源。',
  CVS_alignment_does_not_match_planetary_kinematics: '采集对齐记录与当前行星几何或相对转频不一致。',
  CVS_carrier_phase_does_not_match_reference_speed: '行星架相位与当前参考轴转频不一致。',
}
const COMPUTATION = { computed: '已计算', valid: '有效', approximate: '近似计算', indeterminate: '不可判定', not_evaluable: '不可评估' }
export const compositeCalculationState = state => COMPUTATION[state] || '未知'
export const compositeReason = reason => REASONS[reason] || reason || '—'
export const compositeValue = value => value == null ? '—' : typeof value === 'number'
  ? Number.isFinite(value) ? Number(value.toPrecision(6)).toString() : '—'
  : Array.isArray(value) ? value.map(compositeValue).join(', ') : String(value)
export const compositeStages = result => (result?.analysis?.stages || []).map(stage => ({
  name: stage.name, state: compositeCalculationState(stage.status), reason: compositeReason(stage.reason),
}))
export const compositeMetrics = result => Object.entries(result?.analysis?.metrics || {}).map(([name, value]) => ({ name, value: compositeValue(value) }))
export function buildCompositeRequest(method, rotation, alignmentText = '') {
  const request = { method, options: {} }
  if (rotation != null && rotation !== '') {
    if (!Number.isFinite(Number(rotation)) || Number(rotation) <= 0) throw new Error('恒定参考轴转频必须为正数，单位Hz')
    request.rot_freq_hz = Number(rotation)
  }
  if (method === 'composite_cvs_med_msb' && alignmentText.trim()) {
    try { request.alignment = JSON.parse(alignmentText) } catch { throw new Error('CVS采集对齐记录必须为合法JSON') }
    if (!request.alignment || Array.isArray(request.alignment) || typeof request.alignment !== 'object') {
      throw new Error('CVS采集对齐记录必须为JSON对象')
    }
  }
  return request
}
export function compositeCurves(result) {
  const data = result?.analysis?.data || {}
  const curves = []
  const demodulation = data.demodulation
  if (demodulation?.amplitude_spectrum) curves.push({ title: 'AM 调制谱', ...demodulation.amplitude_spectrum })
  if (demodulation?.frequency_spectrum) curves.push({ title: 'FM 调制谱', ...demodulation.frequency_spectrum })
  const msb = data.slice || data.msb?.data?.slice
  if (msb) curves.push({ title: 'MSB 调制切片', axis_unit: 'Hz', amplitude_unit: msb.amplitude_unit,
    points: (msb.modulation_frequency_hz || []).map((value, index) => [value, msb.magnitude?.[index] ?? null]) })
  if (data.scales) curves.push({ title: '多尺度归一化能量熵', axis_unit: '尺度', amplitude_unit: 'dimensionless',
    points: data.scales.map(item => [item.scale, item.normalized_entropy]) })
  return curves
}
