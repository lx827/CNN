import request from '../utils/request'

export const getSystemLogs = async (lines = 200) => {
  const res = await request.get('/api/logs/', { params: { lines } })
  return res
}

export const requestCollection = async (deviceId) => {
  const res = await request.post(`/api/collect/request?device_id=${deviceId}`)
  return res
}

export const getTaskStatus = async (taskId) => {
  const res = await request.get(`/api/collect/tasks/${taskId}/status`)
  return res
}

export const getCollectionHistory = async (deviceId = null, limit = 20) => {
  const params = { limit }
  if (deviceId) params.device_id = deviceId
  const res = await request.get('/api/collect/history', { params })
  return res
}
