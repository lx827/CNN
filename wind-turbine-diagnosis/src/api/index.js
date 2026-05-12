/**
 * API 接口层
 * 负责调用云端 FastAPI 后端服务，并将后端数据转换为前端需要的格式
 *
 * 后端地址通过 vite.config.js 的 proxy 配置代理到 localhost:8000
 */
import request from '../utils/request'

// ==================== 认证 ====================
export const login = (data) => request.post('/api/auth/login', data)

// ==================== 工具函数 ====================

function calcRms(arr) {
  if (!arr || arr.length === 0) return 0
  const sum = arr.reduce((s, v) => s + v * v, 0)
  return Math.sqrt(sum / arr.length)
}

function calcPeak(arr) {
  if (!arr || arr.length === 0) return 0
  return Math.max(...arr.map(Math.abs))
}

function formatDateTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  }).replace(/\//g, '-')
}

// ==================== Dashboard ====================

export const getStatistics = async () => {
  return {
    code: 200,
    data: {
      faultDistribution: [
        { value: 12, name: 'gear_wear' },
        { value: 8, name: 'bearing_outer_race' },
        { value: 5, name: 'bearing_inner_race' },
        { value: 3, name: 'gear_broken' },
        { value: 2, name: 'bearing_ball' }
      ],
      monthlyTrend: {
        months: ['1月', '2月', '3月', '4月', '5月', '6月'],
        alarms: [3, 5, 4, 7, 2, 4],
        handled: [2, 4, 3, 5, 2, 3]
      }
    }
  }
}

export const getDeviceInfo = async () => {
  const res = await request.get('/api/dashboard/')
  const backend = res.data || {}
  const devices = backend.devices || []
  const diag = backend.diagnosis || {}
  const alarmStats = backend.alarm_stats || {}

  const deviceList = devices.map((device, idx) => {
    const isOffline = device.status === 'offline'
    const dDiag = diag[device.device_id] || {}
    const health = isOffline ? null : (dDiag.health_score || device.health_score || 87)
    const status = isOffline ? 'offline' : (dDiag.status || device.status || 'normal')

    const getComponentInfo = (channelName) => {
      const name = (channelName || '').toLowerCase()
      if (name.includes('轴承')) return { type: '轴承系统', offset: 8 }
      if (name.includes('齿轮') || name.includes('驱动')) return { type: '齿轮系统', offset: 5 }
      if (name.includes('风扇')) return { type: '风扇系统', offset: 0 }
      if (name.includes('轴')) return { type: '轴系', offset: 3 }
      if (name.includes('底座') || name.includes('基础') || name.includes('松动')) return { type: '底座/基础', offset: -2 }
      return { type: channelName || '通用部件', offset: 0 }
    }

    const channelNames = device.channel_names || {}
    const channelCount = device.channel_count || 3
    const components = []
    for (let i = 1; i <= channelCount; i++) {
      const chName = channelNames[String(i)] || `通道${i}`
      const compInfo = getComponentInfo(chName)
      if (isOffline) {
        components.push({
          id: i,
          name: `${compInfo.type}（${chName}）`,
          status: 'offline',
          health: null
        })
      } else {
        const compHealth = Math.min(100, Math.max(0, health + compInfo.offset))
        const compStatus = compHealth > 80 ? 'normal' : compHealth > 60 ? 'warning' : 'fault'
        components.push({
          id: i,
          name: `${compInfo.type}（${chName}）`,
          status: compStatus,
          health: compHealth
        })
      }
    }

    return {
      deviceId: device.device_id,
      deviceName: device.name,
      status: device.status,
      healthScore: device.health_score,
      runHours: device.runtime_hours,
      location: device.location,
      diagnosis: dDiag,
      components,
      alarmCount: alarmStats.total || 0,
    }
  })

  return {
    code: 200,
    data: {
      devices: deviceList,
      alarmStats,
      selectedDevice: deviceList[0] || null,
    }
  }
}

// ==================== Monitor ====================

export const getRealtimeVibrationData = async (preferSpecial = false) => {
  const res = await request.get('/api/monitor/latest', {
    params: { prefer_special: preferSpecial }
  })
  const backendList = res.data || []
  const sensorParams = res.sensor_params || {}

  const defaultChannelNames = ['通道1-轴承附近', '通道2-驱动端', '通道3-风扇端']

  const channels = backendList.map((item, idx) => {
    const data = item.data || []
    const fftFreq = item.fft_freq || []
    const fftAmp = item.fft_amp || []

    return {
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

// ==================== 子模块统一导出 ====================

export * from './data'
export * from './device'
export * from './diagnosis'
export * from './alarm'
export * from './system'
