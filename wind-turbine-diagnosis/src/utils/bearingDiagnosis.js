/**
 * 轴承诊断新响应契约的只读适配。
 * 齿轮结果仍使用 fault_indicators，不得复用本模块读取齿轮指标。
 */

const asObject = value => value && typeof value === 'object' ? value : {}

export const bearingEvaluationIndicators = result => asObject(result?.evaluation?.indicators)

export const scScohIndicators = result => asObject(result?.sc_scoh_indicators)

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

/** 汇总显著指标；SC/SCoh 使用自己的 scoh_snr，不回读旧顶层 fault_indicators。 */
export const significantBearingFaults = result => bearingIndicatorEntries(result)
  .filter(({ info }) => info && typeof info === 'object' && (info.significant || info.critical))
  .map(({ key, name, info, source }) => ({
    key,
    fault_type: name,
    snr: info.snr ?? info.scoh_snr ?? null,
    score: info.score ?? info.value ?? '?',
    detected_hz: info.detected_hz ?? null,
    theory_hz: info.theory_hz ?? null,
    source,
  }))

/** 提取图表标注；统计指标没有频率，自然被过滤。 */
export const bearingFrequencyAnnotations = result => bearingIndicatorEntries(result)
  .map(({ key, name, info, source }) => {
    if (!info || typeof info !== 'object') return null
    const freq = info.detected_hz ?? info.theory_hz ?? info.frequency_hz
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
  return info.value ?? info.snr ?? info.scoh_peak ?? info.scoh_snr ?? info.detected_hz ?? '-'
}
