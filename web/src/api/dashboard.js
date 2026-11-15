/** 设备总览读模型：保留服务端诊断，通道没有独立结果时不生成健康分。 */
import request from '../utils/request'

export const getDeviceInfo = async () => {
  const res = await request.get('/api/dashboard/')
  const backend = res.data || {}
  const deviceList = (backend.devices || []).map(device => {
    const diagnosis = backend.diagnosis?.[device.device_id] || device
    const channelNames = device.channel_names || {}
    return {
      ...device,
      ...diagnosis,
      deviceId: device.device_id,
      deviceName: device.name,
      is_offline: device.is_offline,
      runHours: device.runtime_hours,
      diagnosis,
      components: Array.from({ length: device.channel_count || 3 }, (_, index) => ({
        id: index + 1,
        name: channelNames[String(index + 1)] || `通道${index + 1}`,
        ...diagnosis.channels?.[`ch${index + 1}`],
      })),
    }
  })
  return { code: 200, data: {
    devices: deviceList,
    alarmStats: backend.alarm_stats || {},
    selectedDevice: deviceList[0] || null,
  } }
}
