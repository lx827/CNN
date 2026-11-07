/**
 * 设备总览接口(/api/dashboard)
 * 后端数据 → 前端设备卡片格式转换
 */
import request from '../utils/request'

export const getDeviceInfo = async () => {
  const res = await request.get('/api/dashboard/')
  const backend = res.data || {}
  const devices = backend.devices || []
  const diag = backend.diagnosis || {}
  const alarmStats = backend.alarm_stats || {}

  const deviceList = devices.map((device, idx) => {
    const isOffline = device.status === 'offline'
    const dDiag = diag[device.device_id] || {}
    const health = dDiag.health_score || device.health_score || 87
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
        const compHealth = Math.min(100, Math.max(0, health + compInfo.offset))
        const compStatus = compHealth > 80 ? 'normal' : compHealth > 60 ? 'warning' : 'fault'
        components.push({
          id: i,
          name: `${compInfo.type}（${chName}）`,
          status: compStatus,
          health: compHealth
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
