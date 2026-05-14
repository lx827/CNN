import request from '../utils/request'
import { formatDateTime } from '../utils/format'
import { DEFAULT_HEALTH_SCORE } from '../utils/constants'

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

  const probs = d.fault_probabilities || {}
  const sorted = Object.entries(probs)
    .filter(([k]) => k !== '正常运行')
    .sort((a, b) => b[1] - a[1])

  const faults = []

  if (sorted.length > 0 && sorted[0][1] > 0.2) {
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
          energy: v,
          freq: 180 * (i + 1)
        })),
        probabilities: Object.entries(probs).map(([k, v]) => ({
          type: faultMap[k] || 'normal',
          probability: v
        })).filter(p => p.type !== 'normal')
      })
    }
  }

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
      healthScore: d.health_score || DEFAULT_HEALTH_SCORE,
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
