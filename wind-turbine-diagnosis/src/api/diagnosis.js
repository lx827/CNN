/**
 * 诊断接口(/api/data 下诊断相关端点)
 * 诊断读取/缓存、综合分析、方法级分析、重新诊断
 */
import request from '../utils/request'

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
    detrend: config.detrend ?? false,
    profile: config.profile || 'balanced',
    denoise: config.denoise || 'none',
    max_seconds: config.max_seconds || 5,
  }
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/research-analysis`, { params })
  return res
}

export const getMethodInfo = async () => {
  const res = await request.get('/api/data/method-info')
  return res
}

export const getChannelMethodAnalysis = async (deviceId, batchIndex, channel, method, config = {}) => {
  const params = {
    method,
    denoise: config.denoise || 'none',
    detrend: config.detrend ?? false,
  }
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/method-analysis`, { params })
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
