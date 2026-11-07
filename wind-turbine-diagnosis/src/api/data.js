/**
 * 数据查看接口(/api/data)
 * 设备/批次列表、原始波形与各频谱计算、数据删除与导出
 */
import request from '../utils/request'

export const getDeviceBatches = async (deviceId) => {
  const res = await request.get(`/api/data/${deviceId}/batches`)
  return res
}

export const getChannelData = async (deviceId, batchIndex, channel, detrend = false, denoise = 'none') => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}`, {
    params: { detrend, denoise }
  })
  return res
}

export const getChannelFFT = async (deviceId, batchIndex, channel, maxFreq = 5000, detrend = false, denoise = 'none') => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/fft`, {
    params: { max_freq: maxFreq, detrend, denoise }
  })
  return res
}

export const getChannelSTFT = async (deviceId, batchIndex, channel, maxFreq = 5000, nperseg = 512, noverlap = 256, detrend = false, denoise = 'none') => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/stft`, {
    params: { max_freq: maxFreq, nperseg, noverlap, detrend, denoise }
  })
  return res
}

export const getChannelEnvelope = async (deviceId, batchIndex, channel, maxFreq = 1000, detrend = false, method = 'envelope', denoise = 'none') => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/envelope`, {
    params: { max_freq: maxFreq, detrend, method, denoise }
  })
  return res
}

export const getChannelGear = async (deviceId, batchIndex, channel, detrend = false, method = 'standard', denoise = 'none') => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/gear`, {
    params: { detrend, method, denoise }
  })
  return res
}

export const getChannelOrder = async (deviceId, batchIndex, channel, freqMin = 10, freqMax = 100, samplesPerRev = 1024, maxOrder = 50, detrend = false, denoise = 'none') => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/order`, {
    params: { freq_min: freqMin, freq_max: freqMax, samples_per_rev: samplesPerRev, max_order: maxOrder, detrend, denoise }
  })
  return res
}

export const getChannelCepstrum = async (deviceId, batchIndex, channel, maxQuefrency = 500, detrend = false, denoise = 'none') => {
  const res = await request.get(`/api/data/${deviceId}/${batchIndex}/${channel}/cepstrum`, {
    params: { max_quefrency: maxQuefrency, detrend, denoise }
  })
  return res
}

export const getChannelStats = async (deviceId, batchIndex, channel, windowSize = 1024, step = null, detrend = false, denoise = 'none') => {
  const params = { window_size: windowSize, detrend, denoise }
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

export const exportChannelCSV = (deviceId, batchIndex, channel, detrend = false, denoise = 'none') => {
  const url = `/api/data/${deviceId}/${batchIndex}/${channel}/export?detrend=${detrend}&denoise=${denoise}`
  window.open(url, '_blank')
}
