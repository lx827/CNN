/**
 * 虚拟数据库层
 * 模拟数据库的读写操作，后期替换为真实数据库连接
 * 
 * 后期对接方式：
 * - MySQL: 使用 mysql2 或 Sequelize
 * - PostgreSQL: 使用 pg 或 Prisma
 * - SQLite: 使用 better-sqlite3
 * - MongoDB: 使用 mongoose
 */

// ==================== 虚拟数据库表 ====================

// 设备信息表
const devicesTable = {
  id: 1,
  name: '风机齿轮箱 #01',
  status: 'running',        // running / stopped / maintenance
  healthScore: 87,
  runHours: 12560,
  lastMaintenance: '2024-03-15',
  nextMaintenance: '2024-06-15',
  createdAt: '2023-01-01 00:00:00',
  updatedAt: '2024-04-29 14:30:00'
}

// 部件状态表
const componentsTable = [
  { id: 1, deviceId: 1, name: '高速轴齿轮', status: 'normal', health: 92 },
  { id: 2, deviceId: 1, name: '低速轴齿轮', status: 'normal', health: 88 },
  { id: 3, deviceId: 1, name: '行星齿轮组', status: 'warning', health: 76 },
  { id: 4, deviceId: 1, name: '输入轴轴承', status: 'normal', health: 90 },
  { id: 5, deviceId: 1, name: '输出轴轴承', status: 'warning', health: 72 },
  { id: 6, deviceId: 1, name: '中间轴轴承', status: 'normal', health: 85 }
]

// 振动数据表（实时）
const vibrationDataTable = {
  id: 1001,
  deviceId: 1,
  timestamp: new Date().toISOString(),
  channels: [
    {
      id: 1,
      name: '通道1-水平振动',
      unit: 'mm/s',
      sampleRate: 1000,  // Hz
      timeDomain: [],    // 时域数据数组
      frequency: [],     // 频域数据数组
      rms: 0,
      peak: 0
    },
    {
      id: 2,
      name: '通道2-垂直振动',
      unit: 'mm/s',
      sampleRate: 1000,
      timeDomain: [],
      frequency: [],
      rms: 0,
      peak: 0
    },
    {
      id: 3,
      name: '通道3-轴向振动',
      unit: 'mm/s',
      sampleRate: 1000,
      timeDomain: [],
      frequency: [],
      rms: 0,
      peak: 0
    }
  ],
  sensorParams: {
    rpm: 1485,
    temperature: 68,
    load: 85
  }
}

// 诊断结果表
const diagnosisResultTable = [
  {
    id: 1,
    deviceId: 1,
    diagnosisTime: '2024-04-29 14:32:18',
    overallStatus: 'warning',
    component: '行星齿轮组',
    faultType: '齿面磨损',
    severity: 'medium',       // low / medium / high
    confidence: 0.87,
    description: '检测到特征频率幅值增大，建议检查齿轮啮合状态',
    imfComponents: [
      { name: 'IMF1', energy: 45.2, freq: 125 },
      { name: 'IMF2', energy: 28.6, freq: 250 },
      { name: 'IMF3', energy: 15.8, freq: 375 },
      { name: 'IMF4', energy: 7.4, freq: 500 },
      { name: 'IMF5', energy: 3.0, freq: 625 }
    ],
    probabilities: [
      { type: '齿面磨损', probability: 0.87 },
      { type: '齿轮点蚀', probability: 0.62 },
      { type: '齿轮断齿', probability: 0.23 },
      { type: '正常状态', probability: 0.13 }
    ],
    createdAt: '2024-04-29 14:32:18'
  },
  {
    id: 2,
    deviceId: 1,
    diagnosisTime: '2024-04-29 14:32:18',
    overallStatus: 'warning',
    component: '输出轴轴承',
    faultType: '外圈轻微剥落',
    severity: 'low',
    confidence: 0.74,
    description: '轴承外圈故障特征频率轻微突出，持续监测中',
    imfComponents: [
      { name: 'IMF1', energy: 52.1, freq: 180 },
      { name: 'IMF2', energy: 31.4, freq: 360 },
      { name: 'IMF3', energy: 10.2, freq: 540 },
      { name: 'IMF4', energy: 4.8, freq: 720 },
      { name: 'IMF5', energy: 1.5, freq: 900 }
    ],
    probabilities: [
      { type: '外圈剥落', probability: 0.74 },
      { type: '内圈磨损', probability: 0.35 },
      { type: '滚动体损伤', probability: 0.28 },
      { type: '正常状态', probability: 0.26 }
    ],
    createdAt: '2024-04-29 14:32:18'
  }
]

// 告警记录表
const alarmRecordsTable = [
  { id: 1, deviceId: 1, time: '2024-04-29 14:32:18', component: '行星齿轮组', faultType: '齿面磨损', severity: 'warning', confidence: '87%', status: '待处理' },
  { id: 2, deviceId: 1, time: '2024-04-29 09:15:42', component: '输出轴轴承', faultType: '外圈轻微剥落', severity: 'info', confidence: '74%', status: '监测中' },
  { id: 3, deviceId: 1, time: '2024-04-28 16:23:05', component: '低速轴齿轮', faultType: '齿面点蚀', severity: 'warning', confidence: '82%', status: '已处理' },
  { id: 4, deviceId: 1, time: '2024-04-27 11:45:33', component: '高速轴齿轮', faultType: '轻微磨损', severity: 'info', confidence: '68%', status: '已处理' },
  { id: 5, deviceId: 1, time: '2024-04-26 08:12:19', component: '输入轴轴承', faultType: '润滑不足预警', severity: 'info', confidence: '71%', status: '已处理' },
  { id: 6, deviceId: 1, time: '2024-04-25 15:38:27', component: '中间轴轴承', faultType: '温度异常', severity: 'warning', confidence: '79%', status: '已处理' },
  { id: 7, deviceId: 1, time: '2024-04-24 10:22:41', component: '行星齿轮组', faultType: '啮合频率异常', severity: 'danger', confidence: '91%', status: '已处理' },
  { id: 8, deviceId: 1, time: '2024-04-23 14:55:08', component: '输出轴轴承', faultType: '振动超标', severity: 'danger', confidence: '88%', status: '已处理' }
]

// 统计表
const statisticsTable = {
  faultDistribution: [
    { value: 12, name: '齿轮磨损' },
    { value: 8, name: '轴承损伤' },
    { value: 5, name: '润滑异常' },
    { value: 3, name: '不对中' },
    { value: 2, name: '松动' }
  ],
  monthlyTrend: {
    months: ['1月', '2月', '3月', '4月', '5月', '6月'],
    alarms: [3, 5, 4, 7, 2, 4],
    handled: [2, 4, 3, 5, 2, 3]
  }
}


// ==================== 辅助函数 ====================

// 生成模拟振动波形数据
function generateWaveform(freq, amplitude, noise, length) {
  const data = []
  for (let i = 0; i < length; i++) {
    const t = i / 1000
    const signal = amplitude * Math.sin(2 * Math.PI * freq * t)
    const noiseVal = (Math.random() - 0.5) * noise
    data.push(parseFloat((signal + noiseVal).toFixed(3)))
  }
  return data
}

// 模拟数据库延迟
function simulateDelay(ms = 100) {
  return new Promise(resolve => setTimeout(resolve, ms))
}


// ==================== 数据库操作接口 ====================

/**
 * 获取设备信息（含部件列表）
 * 对应 SQL: SELECT * FROM devices WHERE id = ? + SELECT * FROM components WHERE deviceId = ?
 */
export const queryDeviceInfo = async (deviceId = 1) => {
  await simulateDelay()
  
  return {
    code: 200,
    data: {
      deviceName: devicesTable.name,
      status: devicesTable.status,
      healthScore: devicesTable.healthScore,
      runHours: devicesTable.runHours,
      lastMaintenance: devicesTable.lastMaintenance,
      nextMaintenance: devicesTable.nextMaintenance,
      components: componentsTable.filter(c => c.deviceId === deviceId)
    }
  }
}

/**
 * 获取实时振动数据
 * 对应 SQL: SELECT * FROM vibration_data WHERE deviceId = ? ORDER BY timestamp DESC LIMIT 1
 */
export const queryRealtimeVibration = async (deviceId = 1) => {
  await simulateDelay()
  
  const length = 500
  
  // 模拟数据动态更新
  vibrationDataTable.timestamp = new Date().toISOString()
  vibrationDataTable.channels = [
    {
      id: 1,
      name: '通道1-水平振动',
      unit: 'mm/s',
      sampleRate: 1000,
      timeDomain: generateWaveform(50, 2.5, 0.8, length),
      frequency: generateWaveform(50, 1.8, 0.5, length),
      rms: parseFloat((1.8 + Math.random() * 0.1).toFixed(2)),
      peak: parseFloat((3.4 + Math.random() * 0.2).toFixed(2))
    },
    {
      id: 2,
      name: '通道2-垂直振动',
      unit: 'mm/s',
      sampleRate: 1000,
      timeDomain: generateWaveform(75, 1.8, 0.6, length),
      frequency: generateWaveform(75, 1.2, 0.4, length),
      rms: parseFloat((1.3 + Math.random() * 0.1).toFixed(2)),
      peak: parseFloat((2.6 + Math.random() * 0.2).toFixed(2))
    },
    {
      id: 3,
      name: '通道3-轴向振动',
      unit: 'mm/s',
      sampleRate: 1000,
      timeDomain: generateWaveform(100, 1.2, 0.5, length),
      frequency: generateWaveform(100, 0.9, 0.3, length),
      rms: parseFloat((0.95 + Math.random() * 0.1).toFixed(2)),
      peak: parseFloat((1.8 + Math.random() * 0.2).toFixed(2))
    }
  ]
  vibrationDataTable.sensorParams = {
    rpm: parseFloat((1485 + Math.random() * 10 - 5).toFixed(1)),
    temperature: parseFloat((68 + Math.random() * 4 - 2).toFixed(1)),
    load: parseFloat((85 + Math.random() * 10 - 5).toFixed(1))
  }

  return {
    code: 200,
    data: {
      timestamp: vibrationDataTable.timestamp,
      channels: vibrationDataTable.channels,
      sensorParams: vibrationDataTable.sensorParams
    }
  }
}

/**
 * 获取故障诊断结果
 * 对应 SQL: SELECT * FROM diagnosis_result WHERE deviceId = ? ORDER BY diagnosisTime DESC
 */
export const queryDiagnosisResult = async (deviceId = 1) => {
  await simulateDelay()
  
  const results = diagnosisResultTable.filter(r => r.deviceId === deviceId)
  
  return {
    code: 200,
    data: {
      diagnosisTime: results[0]?.diagnosisTime || '',
      overallStatus: results[0]?.overallStatus || 'normal',
      faults: results
    }
  }
}

/**
 * 获取历史告警记录（支持分页）
 * 对应 SQL: SELECT * FROM alarm_records WHERE deviceId = ? ORDER BY time DESC LIMIT ? OFFSET ?
 */
export const queryAlarmRecords = async (deviceId = 1, page = 1, pageSize = 10) => {
  await simulateDelay()
  
  const records = alarmRecordsTable.filter(r => r.deviceId === deviceId)
  const total = records.length
  const start = (page - 1) * pageSize
  const list = records.slice(start, start + pageSize)
  
  return {
    code: 200,
    data: {
      total,
      list
    }
  }
}

/**
 * 获取统计数据
 * 对应 SQL: 聚合查询 faultDistribution 和 monthlyTrend
 */
export const queryStatistics = async () => {
  await simulateDelay()
  
  return {
    code: 200,
    data: statisticsTable
  }
}

/**
 * 插入告警记录
 * 对应 SQL: INSERT INTO alarm_records (...) VALUES (...)
 */
export const insertAlarm = async (alarmData) => {
  await simulateDelay()
  
  const newAlarm = {
    id: alarmRecordsTable.length + 1,
    deviceId: 1,
    time: new Date().toLocaleString('zh-CN'),
    ...alarmData
  }
  
  alarmRecordsTable.unshift(newAlarm)
  
  return {
    code: 200,
    data: newAlarm,
    message: '告警记录已插入'
  }
}

/**
 * 更新告警状态
 * 对应 SQL: UPDATE alarm_records SET status = ? WHERE id = ?
 */
export const updateAlarmStatus = async (alarmId, newStatus) => {
  await simulateDelay()
  
  const alarm = alarmRecordsTable.find(a => a.id === alarmId)
  if (!alarm) {
    return { code: 404, message: '告警记录不存在' }
  }
  
  alarm.status = newStatus
  
  return {
    code: 200,
    data: alarm,
    message: '告警状态已更新'
  }
}

/**
 * 更新设备健康度
 * 对应 SQL: UPDATE devices SET healthScore = ?, updatedAt = ? WHERE id = ?
 */
export const updateDeviceHealth = async (deviceId, healthScore) => {
  await simulateDelay()
  
  devicesTable.healthScore = healthScore
  devicesTable.updatedAt = new Date().toLocaleString('zh-CN')
  
  return {
    code: 200,
    data: devicesTable,
    message: '设备健康度已更新'
  }
}
