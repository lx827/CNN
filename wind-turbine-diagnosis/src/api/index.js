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
  // 后端暂无独立统计接口，用 dashboard 数据 + 静态模拟
  // 实际生产环境应让后端提供真实统计
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

  // 为每个设备生成部件状态（模拟数据）
  const deviceList = devices.map((device, idx) => {
    const isOffline = device.status === 'offline'
    const dDiag = diag[device.device_id] || {}
    const health = isOffline ? null : (dDiag.health_score || device.health_score || 87)
    const status = isOffline ? 'offline' : (dDiag.status || device.status || 'normal')

    // 根据设备通道名称生成对应的部件状态
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
    // 使用后端返回的真实 FFT 频谱数据
    const fftFreq = item.fft_freq || []
    const fftAmp = item.fft_amp || []

    return {
      id: item.channel || idx + 1,
      name: item.channel_name || defaultChannelNames[idx] || `通道${idx + 1}`,
      channel_name: item.channel_name || defaultChannelNames[idx] || `通道${idx + 1}`,
      unit: 'mm/s',
      sampleRate: item.sample_rate || 25600,
      timeDomain: data,
      frequency: fftAmp,       // 频域幅值数组
      fftFreq: fftFreq,        // 频域频率轴 (Hz)
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

// ==================== Diagnosis ====================

export const getFaultDiagnosisResult = async (deviceId = 'WTG-001') => {
  const res = await request.get('/api/diagnosis/', {
    params: { device_id: deviceId }
  })
  const d = res.data || {}

  const faultMap = {
    '齿轮磨损': 'wear',
    '轴承内圈故障': 'inner_race',
    '轴承外圈故障': 'outer_race',
    '轴承滚动体故障': 'ball',

    '正常运行': 'normal',
    '齿轮断齿': 'broken',
    '齿轮缺齿': 'missing',
    '齿轮齿根裂纹': 'rootcrack'
  }

  const faultNameMap = {
    wear: '齿轮磨损',
    inner_race: '轴承内圈故障',
    outer_race: '轴承外圈故障',
    ball: '轴承滚动体故障',
    broken: '齿轮断齿',
    missing: '齿轮缺齿',
    rootcrack: '齿轮齿根裂纹',
    normal: '正常运行'
  }

  const componentMap = {
    wear: '高速轴齿轮',
    broken: '高速轴齿轮',
    missing: '低速轴齿轮',
    rootcrack: '低速轴齿轮',
    inner_race: '输入轴轴承',
    outer_race: '输出轴轴承',
    ball: '中间轴轴承',

    normal: '整体'
  }

  // 把后端的 fault_probabilities 转换成前端需要的 faults 数组
  // 取概率最高的两个非 normal 故障，如果都正常则只显示一个
  const probs = d.fault_probabilities || {}
  const sorted = Object.entries(probs)
    .filter(([k]) => k !== '正常运行')
    .sort((a, b) => b[1] - a[1])

  const faults = []

  if (sorted.length > 0 && sorted[0][1] > 0.2) {
    // 第一个故障
    const [name1, prob1] = sorted[0]
    const type1 = faultMap[name1] || 'wear'
    faults.push({
      id: 1,
      deviceId: 1,
      diagnosisTime: formatDateTime(d.analyzed_at),
      overallStatus: d.status || 'normal',
      component: componentMap[type1] || '未知部件',
      faultType: type1,
      severity: prob1 > 0.6 ? 'high' : prob1 > 0.3 ? 'medium' : 'low',
      confidence: prob1,
      description: `检测到${name1}特征频率幅值异常，建议重点排查${componentMap[type1] || '相关部件'}。`,
      imfComponents: Object.entries(d.imf_energy || {}).map(([k, v], i) => ({
        name: k,
        energy: v,
        freq: 125 * (i + 1)
      })),
      probabilities: Object.entries(probs).map(([k, v]) => ({
        type: faultMap[k] || 'normal',
        probability: v
      })).filter(p => p.type !== 'normal')
    })

    // 第二个故障（如果有且概率>0.1）
    if (sorted.length > 1 && sorted[1][1] > 0.1) {
      const [name2, prob2] = sorted[1]
      const type2 = faultMap[name2] || 'outer_race'
      faults.push({
        id: 2,
        deviceId: 1,
        diagnosisTime: formatDateTime(d.analyzed_at),
        overallStatus: d.status || 'normal',
        component: componentMap[type2] || '未知部件',
        faultType: type2,
        severity: prob2 > 0.6 ? 'high' : prob2 > 0.3 ? 'medium' : 'low',
        confidence: prob2,
        description: `检测到${name2}特征频率轻微突出，持续监测中。`,
        imfComponents: Object.entries(d.imf_energy || {}).map(([k, v], i) => ({
          name: k,
          energy: v * (0.8 + Math.random() * 0.4),
          freq: 180 * (i + 1)
        })),
        probabilities: Object.entries(probs).map(([k, v]) => ({
          type: faultMap[k] || 'normal',
          probability: v
        })).filter(p => p.type !== 'normal')
      })
    }
  }

  // 如果没有任何故障，给一个默认的正常提示
  if (faults.length === 0) {
    faults.push({
      id: 1,
      deviceId: 1,
      diagnosisTime: formatDateTime(d.analyzed_at),
      overallStatus: 'normal',
      component: '整体',
      faultType: 'normal',
      severity: 'low',
      confidence: 0.95,
      description: '设备运行正常，未发现明显故障特征。',
      imfComponents: Object.entries(d.imf_energy || {}).map(([k, v], i) => ({
        name: k,
        energy: v,
        freq: 125 * (i + 1)
      })),
      probabilities: [{ type: 'normal', probability: 0.95 }]
    })
  }

  return {
    code: 200,
    data: {
      diagnosisTime: formatDateTime(d.analyzed_at),
      overallStatus: d.status || 'normal',
      healthScore: d.health_score || 87,
      faultProbabilities: d.fault_probabilities || {},
      batchIndex: d.batch_index || 0,
      orderAnalysis: d.order_analysis || null,
      rotFreq: d.rot_freq || null,
      engineResult: d.engine_result || null,
      channelsDetail: d.channels_detail || null,
      faults
    }
  }
}

// ==================== Alarm ====================

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

// 处理告警（标记为已处理）
export const updateAlarmStatus = async (alarmId, newStatus) => {
  const res = await request.post(`/api/alarms/${alarmId}/resolve`)
  return res
}

// 删除告警
export const deleteAlarm = async (alarmId) => {
  const res = await request.delete(`/api/alarms/${alarmId}`)
  return res
}


// ==================== 采集任务 ====================

export const requestCollection = async (deviceId) => {
  const res = await request.post(`/api/collect/request?device_id=${deviceId}`)
  return res
}

export const getTaskStatus = async (taskId) => {
  const res = await request.get(`/api/collect/tasks/${taskId}/status`)
  return res
}

// ==================== 数据查看（设备、批次、FFT、STFT）====================

export const getDevices = async () => {
  const res = await request.get('/api/devices/')
  return res
}

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

// ==================== 设备配置（边端参数）====================

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

export const exportChannelCSV = (deviceId, batchIndex, channel, detrend = false) => {
  const url = `/api/data/${deviceId}/${batchIndex}/${channel}/export?detrend=${detrend}`
  window.open(url, '_blank')
}

// ==================== 系统日志 ====================

export const getSystemLogs = async (lines = 200) => {
  const res = await request.get('/api/logs/', { params: { lines } })
  return res
}
