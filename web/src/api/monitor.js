/**
 * 实时监测接口(/api/monitor)
 * 最新批次振动数据与历史批次查询
 */
import request from '../utils/request'
import { calcRms, calcPeak } from '../utils/math'

export const getRealtimeVibrationData = async (deviceId = 'WTG-001', preferSpecial = false) => {
  const res = await request.get('/api/monitor/latest', {
    params: { device_id: deviceId, prefer_special: preferSpecial }
  })
  const backendList = res.data || []
  const sensorParams = res.sensor_params || {}

  const defaultChannelNames = ['通道1-轴承附近', '通道2-驱动端', '通道3-风扇端']

  const channels = backendList.map((item, idx) => {
    const data = item.data || []
    const fftFreq = item.fft_freq || []
    const fftAmp = item.fft_amp || []

    return {
      ...item,
      id: item.channel || idx + 1,
      name: item.channel_name || defaultChannelNames[idx] || `通道${idx + 1}`,
      channel_name: item.channel_name || defaultChannelNames[idx] || `通道${idx + 1}`,
      unit: 'mm/s',
      sampleRate: item.sample_rate || 25600,
      timeDomain: data,
      frequency: fftAmp,
      fftFreq: fftFreq,
      rms: parseFloat(calcRms(data).toFixed(2)),
      peak: parseFloat(calcPeak(data).toFixed(2))
    }
  })

  return {
    code: 200,
    data: {
      timestamp: backendList[0]?.timestamp || new Date().toISOString(),
      channels,
      sensorParams
    }
  }
}

export const getMonitorHistory = async (deviceId = 'WTG-001', channel = 1, batches = 16, includeSpecial = true) => {
  const res = await request.get('/api/monitor/history', {
    params: { device_id: deviceId, channel, batches, include_special: includeSpecial }
  })
  return res
}
