import request from '../utils/request'

// 获取设备信息（模拟数据）
export const getDeviceInfo = () => {
  return Promise.resolve({
    code: 200,
    data: {
      deviceName: '风机齿轮箱 #01',
      status: 'running',
      healthScore: 87,
      runHours: 12560,
      lastMaintenance: '2024-03-15',
      nextMaintenance: '2024-06-15',
      components: [
        { name: '高速轴齿轮', status: 'normal', health: 92 },
        { name: '低速轴齿轮', status: 'normal', health: 88 },
        { name: '行星齿轮组', status: 'warning', health: 76 },
        { name: '输入轴轴承', status: 'normal', health: 90 },
        { name: '输出轴轴承', status: 'warning', health: 72 },
        { name: '中间轴轴承', status: 'normal', health: 85 }
      ]
    }
  })
}

// 获取实时振动数据（模拟数据）
export const getRealtimeVibrationData = () => {
  // 生成模拟正弦波数据
  const generateWaveform = (freq, amplitude, noise, length) => {
    const data = []
    for (let i = 0; i < length; i++) {
      const t = i / 1000
      const signal = amplitude * Math.sin(2 * Math.PI * freq * t)
      const noiseVal = (Math.random() - 0.5) * noise
      data.push(parseFloat((signal + noiseVal).toFixed(3)))
    }
    return data
  }

  const length = 500
  return Promise.resolve({
    code: 200,
    data: {
      timestamp: new Date().toLocaleTimeString(),
      channels: [
        {
          name: '通道1-水平振动',
          unit: 'mm/s',
          timeDomain: generateWaveform(50, 2.5, 0.8, length),
          frequency: generateWaveform(50, 1.8, 0.5, length),
          rms: 1.85,
          peak: 3.42
        },
        {
          name: '通道2-垂直振动',
          unit: 'mm/s',
          timeDomain: generateWaveform(75, 1.8, 0.6, length),
          frequency: generateWaveform(75, 1.2, 0.4, length),
          rms: 1.32,
          peak: 2.68
        },
        {
          name: '通道3-轴向振动',
          unit: 'mm/s',
          timeDomain: generateWaveform(100, 1.2, 0.5, length),
          frequency: generateWaveform(100, 0.9, 0.3, length),
          rms: 0.98,
          peak: 1.85
        }
      ],
      sensorParams: {
        rpm: 485 + Math.random() * 10 - 5,
        temperature: 68 + Math.random() * 4 - 2,
        load: 85 + Math.random() * 10 - 5
      }
    }
  })
}

// 获取故障诊断结果（模拟数据）
export const getFaultDiagnosisResult = () => {
  return Promise.resolve({
    code: 200,
    data: {
      diagnosisTime: '2024-04-29 14:32:18',
      overallStatus: 'warning',
      faults: [
        {
          component: '行星齿轮组',
          faultType: '齿面磨损',
          severity: 'medium',
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
          ]
        },
        {
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
          ]
        }
      ]
    }
  })
}

// 获取历史告警记录（模拟数据）
export const getHistoryAlarmList = () => {
  return Promise.resolve({
    code: 200,
    data: {
      total: 28,
      list: [
        {
          id: 1,
          time: '2024-04-29 14:32:18',
          component: '行星齿轮组',
          faultType: '齿面磨损',
          severity: 'warning',
          confidence: '87%',
          status: '待处理'
        },
        {
          id: 2,
          time: '2024-04-29 09:15:42',
          component: '输出轴轴承',
          faultType: '外圈轻微剥落',
          severity: 'info',
          confidence: '74%',
          status: '监测中'
        },
        {
          id: 3,
          time: '2024-04-28 16:23:05',
          component: '低速轴齿轮',
          faultType: '齿面点蚀',
          severity: 'warning',
          confidence: '82%',
          status: '已处理'
        },
        {
          id: 4,
          time: '2024-04-27 11:45:33',
          component: '高速轴齿轮',
          faultType: '轻微磨损',
          severity: 'info',
          confidence: '68%',
          status: '已处理'
        },
        {
          id: 5,
          time: '2024-04-26 08:12:19',
          component: '输入轴轴承',
          faultType: '润滑不足预警',
          severity: 'info',
          confidence: '71%',
          status: '已处理'
        },
        {
          id: 6,
          time: '2024-04-25 15:38:27',
          component: '中间轴轴承',
          faultType: '温度异常',
          severity: 'warning',
          confidence: '79%',
          status: '已处理'
        },
        {
          id: 7,
          time: '2024-04-24 10:22:41',
          component: '行星齿轮组',
          faultType: '啮合频率异常',
          severity: 'danger',
          confidence: '91%',
          status: '已处理'
        },
        {
          id: 8,
          time: '2024-04-23 14:55:08',
          component: '输出轴轴承',
          faultType: '振动超标',
          severity: 'danger',
          confidence: '88%',
          status: '已处理'
        }
      ]
    }
  })
}

// 获取统计数据（模拟数据）
export const getStatistics = () => {
  return Promise.resolve({
    code: 200,
    data: {
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
  })
}
