import request from '../utils/request'

export const getDeviceBatches = async (deviceId) => {
  const res = await request.get(`/api/data/${deviceId}/batches`)
  return res
}

export const getChannelData = async (deviceId, batchIndex, channel, detrend = false) => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}`, {
    params: { detrend }
  })
  return res
}

export const getChannelFFT = async (deviceId, batchIndex, channel, maxFreq = 5000, detrend = false) => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/fft`, {
    params: { max_freq: maxFreq, detrend }
  })
  return res
}

export const getChannelSTFT = async (deviceId, batchIndex, channel, maxFreq = 5000, nperseg = 512, noverlap = 256, detrend = false) => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/stft`, {
    params: { max_freq: maxFreq, nperseg, noverlap, detrend }
  })
  return res
}

export const getChannelEnvelope = async (deviceId, batchIndex, channel, maxFreq = 1000, detrend = false, method = 'envelope') => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/envelope`, {
    params: { max_freq: maxFreq, detrend, method }
  })
  return res
}

export const getChannelGear = async (deviceId, batchIndex, channel, detrend = false, method = 'standard', denoise = 'none') => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/gear`, {
    params: { detrend, method, denoise }
  })
  return res
}

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

export const getChannelOrder = async (deviceId, batchIndex, channel, freqMin = 10, freqMax = 100, samplesPerRev = 1024, maxOrder = 50, detrend = false) => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/order`, {
    params: { freq_min: freqMin, freq_max: freqMax, samples_per_rev: samplesPerRev, max_order: maxOrder, detrend }
  })
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

export const getChannelCepstrum = async (deviceId, batchIndex, channel, maxQuefrency = 500, detrend = false) => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/cepstrum`, {
    params: { max_quefrency: maxQuefrency, detrend }
  })
  return res
}

export const getChannelStats = async (deviceId, batchIndex, channel, windowSize = 1024, step = null, detrend = false) => {
  const params = { window_size: windowSize, detrend }
  if (step !== null) params.step = step
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/stats`, { params })
  return res
}

export const getAllDeviceData = async () => {
  const res = await request.get('/api/data/devices')
  return res
}

export const deleteBatch = async (deviceId, batchIndex) => {
  const res = await request.delete(`/api/data/${deviceId}/${batchIndex}`)
  return res
}

export const deleteSpecialBatches = async (deviceId) => {
  const res = await request.delete(`/api/data/${deviceId}/special`)
  return res
}

export const exportChannelCSV = (deviceId, batchIndex, channel, detrend = false) => {
  const url = `/api/data/${deviceId}/${batchIndex}/${channel}/export?detrend=${detrend}`
  window.open(url, '_blank')
}
