import request from '../utils/request'

function formatDateTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  }).replace(/\//g, '-')
}

export const getHistoryAlarmList = async (page = 1, pageSize = 10, filters = {}) => {
  const params = { page, size: pageSize }
  if (filters.level) params.level = filters.level
  if (filters.resolved !== undefined) params.resolved = filters.resolved
  if (filters.device_id) params.device_id = filters.device_id
  const res = await request.get('/api/alarms/', { params })
  const backend = res.data || {}
  const items = backend.items || []

  const list = items.map(item => ({
    id: item.id,
    device_id: item.device_id,
    batch_index: item.batch_index,
    time: formatDateTime(item.created_at),
    level: item.level,
    category: item.category,
    title: item.title,
    description: item.description,
    suggestion: item.suggestion,
    channel: item.channel,
    channel_name: item.channel_name,
    is_resolved: item.is_resolved,
    status: item.is_resolved ? '已处理' : '待处理',
  }))

  return {
    code: 200,
    data: {
      total: backend.total || 0,
      list
    }
  }
}

export const updateAlarmStatus = async (alarmId, newStatus) => {
  const res = await request.post(`/api/alarms/${alarmId}/resolve`)
  return res
}

export const deleteAlarm = async (alarmId) => {
  const res = await request.delete(`/api/alarms/${alarmId}`)
  return res
}
