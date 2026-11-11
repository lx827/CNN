/**
 * 诊断接口(/api/data 下诊断相关端点)
 * 诊断读取/缓存、综合分析、方法级分析、重新诊断
 */
import request from '../utils/request'

const advancedBearingParams = config => ({
  ...(config.rot_freq_hz > 0 ? { rot_freq_hz: config.rot_freq_hz } : {}),
  ...(config.target_fault ? { target_fault: config.target_fault } : {}),
  ...(config.target_frequency_hz > 0 ? { target_frequency_hz: config.target_frequency_hz } : {}),
  ...(config.period_samples > 0 ? { period_samples: config.period_samples } : {}),
  ...(config.comb_frequencies_hz?.length ? { comb_frequencies_hz: config.comb_frequencies_hz } : {}),
  ...(config.comb_is_stable === true ? { comb_is_stable: true } : {}),
})

export const getChannelDiagnosis = async (deviceId, batchIndex, channel, denoiseMethod = null) => {
  const params = {}
  if (denoiseMethod) params.denoise_method = denoiseMethod
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/diagnosis`, { params })
  return res
}

export const getChannelAnalyze = async (deviceId, batchIndex, channel, config = {}) => {
  const params = {
    detrend: config.detrend ?? false,
    strategy: config.strategy || 'standard',
    bearing_method: config.bearing_method || 'envelope',
    gear_method: config.gear_method || 'standard',
    denoise: config.denoise || 'none',
  }
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/analyze`, { params })
  return res
}

export const getChannelFullAnalysis = async (deviceId, batchIndex, channel, config = {}) => {
  const params = {
    detrend: config.detrend ?? false,
    denoise: config.denoise || 'none',
  }
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/full-analysis`, { params })
  return res
}

export const getChannelResearchAnalysis = async (deviceId, batchIndex, channel, config = {}) => {
  const params = {
    ...advancedBearingParams(config),
    detrend: config.detrend ?? false,
    profile: config.profile || 'balanced',
    denoise: config.denoise || 'none',
    max_seconds: config.max_seconds || 5,
  }
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/research-analysis`, { params, paramsSerializer: { indexes: null } })
  return res
}

export const getMethodInfo = async () => {
  const res = await request.get('/api/data/method-info')
  return res
}

export const runCompositeResearch = (deviceId, batchIndex, channel, body) =>
  request.post(`/api/data/${deviceId}/${batchIndex}/${channel}/composite-analysis`, body)

export const getChannelMethodAnalysis = async (deviceId, batchIndex, channel, method, config = {}) => {
  const params = {
    ...advancedBearingParams(config),
    method,
    denoise: config.denoise || 'none',
    detrend: config.detrend ?? false,
  }
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/method-analysis`, { params, paramsSerializer: { indexes: null } })
  return res
}

export const updateBatchDiagnosis = async (deviceId, batchIndex, data) => {
  const res = await request.put(`/api/data/${deviceId}/${batchIndex}/diagnosis`, data)
  return res
}

export const reanalyzeBatch = async (deviceId, batchIndex) => {
  const res = await request.post(`/api/data/${deviceId}/${batchIndex}/reanalyze`)
  return res
}

export const reanalyzeAllDevice = async (deviceId) => {
  const res = await request.post(`/api/data/${deviceId}/reanalyze-all`)
  return res
}
