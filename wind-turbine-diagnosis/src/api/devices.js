/**
 * 设备配置接口(/api/devices)
 * 设备列表、边端采集配置、机械参数、告警阈值
 */
import request from '../utils/request'

export const getDevices = async () => {
  const res = await request.get('/api/devices/')
  return res
}

export const getDeviceConfig = async (deviceId) => {
  const res = await request.get(`/api/devices/${deviceId}/config`)
  return res
}

export const updateDeviceConfig = async (deviceId, config) => {
  const res = await request.put(`/api/devices/${deviceId}/config`, config)
  return res
}

export const updateBatchDeviceConfig = async (config) => {
  const res = await request.put('/api/devices/batch-config', config)
  return res
}

export const getAlarmThresholds = async (deviceId) => {
  const res = await request.get(`/api/devices/${deviceId}/alarm-thresholds`)
  return res
}

export const updateAlarmThresholds = async (deviceId, thresholds) => {
  const res = await request.put(`/api/devices/${deviceId}/alarm-thresholds`, { alarm_thresholds: thresholds })
  return res
}
