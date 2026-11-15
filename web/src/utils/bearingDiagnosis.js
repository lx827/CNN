/**
 * 轴承诊断新响应契约的只读适配。
 * 齿轮结果仍使用 fault_indicators，不得复用本模块读取齿轮指标。
 */

const asObject = value => value && typeof value === 'object' ? value : {}

export const bearingReasonText = reason => ({
  missing_stable_comb_frequencies: '请提供稳定梳状基频并确认整段稳定',
  time_varying_comb_requires_time_frequency_model: '未确认梳状频率稳定；时变梳状干扰需要时频模型',
  missing_explicit_target_fault: '未选择周期故障目标，本次实际执行 MED',
  missing_target_frequency_or_period: '缺少目标频率或周期，请配置几何与恒定转频',
  missing_cyclic_candidates_or_geometry_and_rotation: '缺少可靠的循环频率候选，请配置轴承几何与转频',
  zero_energy: '信号无有效能量，无法评估',
  no_impulsive_band_above_threshold: '没有达到工程阈值的冲击频带，无法据此判断健康',
  numerical_deconvolution_failure: '解卷积数值不可判定',
  insufficient_signal_length: '信号长度不足以评估本方法',
  varying_speed_requires_continuous_phase_pipeline: '当前变速工况需要连续相位分析',
})[reason] || '当前输入不满足方法的评估条件'

export const bearingEvaluationIndicators = result => result?.evaluation_kind === 'sc_scoh'
  ? {} : asObject(result?.evaluation?.indicators)

export const scScohIndicators = result => result?.evaluation_kind === 'sc_scoh'
  ? asObject(result?.evaluation?.indicators) : {}

const indicatorEntries = (indicators, source) => Object.entries(asObject(indicators)).map(([name, info]) => ({
  key: `${source}:${name}`,
  name,
  info,
  source,
}))

export const bearingEvaluationEntries = result => indicatorEntries(
  bearingEvaluationIndicators(result),
  'evaluation',
)

export const scScohEntries = result => indicatorEntries(scScohIndicators(result), 'sc_scoh')

export const bearingIndicatorEntries = result => [
  ...bearingEvaluationEntries(result),
  ...scScohEntries(result),
]

/** 汇总显著指标；SC/SCoh 使用专属峰背景比，不回读旧顶层字段。 */
export const significantBearingFaults = result => bearingIndicatorEntries(result)
  .filter(({ info }) => info && typeof info === 'object' && (info.significant || info.critical))
  .map(({ key, name, info, source }) => ({
    key,
    fault_type: name,
    snr: info.snr ?? null,
    score: info.score ?? info.value ?? '?',
    detected_hz: info.detected_hz ?? info.detected_cyclic_frequency_hz ?? null,
    theory_hz: info.theory_hz ?? info.theory_cyclic_frequency_hz ?? null,
    coherence_background_ratio: info.coherence_background_ratio ?? null,
    source,
  }))

/** 提取图表标注；统计指标没有频率，自然被过滤。 */
export const bearingFrequencyAnnotations = result => bearingIndicatorEntries(result)
  .map(({ key, name, info, source }) => {
    if (!info || typeof info !== 'object') return null
    const freq = info.detected_hz ?? info.detected_cyclic_frequency_hz
      ?? info.theory_hz ?? info.theory_cyclic_frequency_hz ?? info.frequency_hz
    if (!Number.isFinite(freq) || freq <= 0) return null
    return {
      key,
      freq,
      name,
      detected: Boolean(info.significant || info.critical),
      type: source === 'sc_scoh' ? 'bearing_sc_scoh' : 'bearing',
    }
  })
  .filter(Boolean)

export const indicatorDisplayValue = info => {
  if (!info || typeof info !== 'object') return '-'
  return info.value ?? info.snr ?? info.scoh_peak ?? info.detected_hz ?? '-'
}

export const bearingMethodLabel = (key) => {
  const map = {
    envelope: '标准包络分析',
    filter_bank_sk: '二叉滤波器组谱峭度',
    cpw: 'CPW预白化+包络',
    teager: 'TEO能量算子+包络',
    spectral_kurtosis: '自适应谱峭度包络',
    med: 'MED最小熵解卷积+包络',
    mckd: 'MCKD最大相关峭度解卷积+包络',
    sc_scoh: '谱相关/谱相干',
    wp: 'WP小波包+包络',
    dwt: 'DWT离散小波+包络',
    emd_envelope: 'EMD经验模态+包络',
    ceemdan_envelope: 'CEEMDAN互补集合+包络',
    vmd_envelope: 'VMD变分模态+包络',
  }
  return map[key] || key
}
