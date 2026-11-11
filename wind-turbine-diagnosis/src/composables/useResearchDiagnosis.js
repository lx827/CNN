/**
 * ResearchDiagnosis 高级诊断页数据与运行逻辑
 *
 * 职责:设备/批次/通道选择、方法元信息加载、单方法/全方法/集成三种模式
 *       的分析与结果派生(投票行、D-S 融合行、全方法摘要行)、路由联动。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { getAllDeviceData } from '../api/data'
import { getMethodInfo, getChannelMethodAnalysis, getChannelResearchAnalysis, runCompositeResearch } from '../api/diagnosis'
import { buildCompositeRequest } from '../utils/compositeResearch'
import { getDiagnosisStatusView } from '../utils/diagnosisStatus'
import { formatErrorMessage } from '../utils/errorMessage'
import {
  bearingIndicatorEntries,
  indicatorDisplayValue,
  significantBearingFaults,
  bearingReasonText,
} from '../utils/bearingDiagnosis'

export const runModeOptions = [
  { label: '单方法', value: 'single' },
  { label: '全部方法', value: 'all' },
  { label: '集成诊断', value: 'ensemble' },
]

export const fmt = value => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(4) : '-'
}

export const percent = value => {
  const num = Number(value)
  return Number.isFinite(num) ? `${(num * 100).toFixed(1)}%` : '-'
}

export const statusType = status => getDiagnosisStatusView(status).tagType

export const statusText = status => getDiagnosisStatusView(status).text

export const evaluationStatusType = status => status === 'evaluated' ? 'success' : 'info'

export const evaluationStatusText = status => {
  if (status === 'indeterminate') return '不可判定'
  if (status === 'not_evaluable') return '不可评估'
  if (status === 'evaluated') return '已评估'
  return status || '不可判定'
}

const voteRows = (votes = {}) => Object.entries(votes).map(([method, value]) => ({
  method,
  confidence: value.confidence ?? 0,
  evaluable: value.evaluable !== false,
  reason: value.reason ? bearingReasonText(value.reason) : '',
  param_hits: value.param_hits ?? '-',
  stat_hits: value.stat_hits ?? '-',
  critical_hits: value.critical_hits ?? '-',
  warning_hits: value.warning_hits ?? '-',
  strongest_score: value.strongest_score ?? '-',
  hits: Array.isArray(value.hits) ? value.hits.join(', ') : '',
}))

const appendIndicator = (rows, source, name, value) => {
  if (!value || typeof value !== 'object') return
  const notEvaluable = value.evaluable === false
    || ('significant' in value && value.significant == null && value.evaluable !== true)
  const isCritical = !notEvaluable && (value.critical || value.significant)
  const isWarning = !notEvaluable && value.warning
  rows.push({
    source,
    name,
    value: indicatorDisplayValue(value),
    state: notEvaluable ? '不可评估' : isCritical ? '命中' : isWarning ? '预警' : '正常',
    type: notEvaluable ? 'info' : isCritical ? 'danger' : isWarning ? 'warning' : 'success',
  })
}

const appendIndicators = (rows, source, indicators = {}) => {
  Object.entries(indicators || {}).forEach(([name, value]) => appendIndicator(rows, source, name, value))
}

const appendBearingIndicators = (rows, source, result) => {
  bearingIndicatorEntries(result).forEach(({ name, info }) => appendIndicator(rows, source, name, info))
}

export function useResearchDiagnosis() {
  const route = useRoute()
  const router = useRouter()
  const devices = ref([])
  const selectedDeviceId = ref('')
  const selectedBatchIndex = ref(null)
  const selectedChannel = ref(1)
  const runMode = ref('single')
  const selectedMethod = ref('envelope')
  const targetFault = ref('')
  const combFrequencies = ref('')
  const combIsStable = ref(false)
  const rotFrequency = ref(null)
  const compositeAlignment = ref('')
  const denoise = ref('none')
  const profile = ref('balanced')
  const loading = ref(false)
  const result = ref(null)
  const methodInfoData = ref({})

  const currentDevice = computed(() => devices.value.find(d => d.device_id === selectedDeviceId.value))
  const currentBatches = computed(() => currentDevice.value?.batches || [])
  const currentChannels = computed(() => {
    const count = currentDevice.value?.channel_count || 3
    const names = currentDevice.value?.channel_names || {}
    return Array.from({ length: count }, (_, i) => ({
      value: i + 1,
      label: names[String(i + 1)] || `通道 ${i + 1}`,
    }))
  })
  const canRun = computed(() => selectedDeviceId.value && selectedBatchIndex.value != null && selectedChannel.value)

  // 方法分组
  const bearingMethodGroup = computed(() =>
    Object.entries(methodInfoData.value).filter(([_, m]) => m.category === 'bearing').map(([k, m]) => ({ key: k, label: m.label }))
  )
  const gearMethodGroup = computed(() =>
    Object.entries(methodInfoData.value).filter(([_, m]) => m.category === 'gear').map(([k, m]) => ({ key: k, label: m.label }))
  )
  const planetaryMethodGroup = computed(() =>
    Object.entries(methodInfoData.value).filter(([_, m]) => m.category === 'planetary').map(([k, m]) => ({ key: k, label: m.label }))
  )
  const compositeMethodGroup = computed(() =>
    Object.entries(methodInfoData.value).filter(([, method]) => method.category === 'composite')
      .map(([key, method]) => ({ key, label: method.label }))
  )

  const selectedMethodInfo = computed(() => methodInfoData.value[selectedMethod.value] || null)
  const methodCategoryTag = computed(() => {
    const cat = selectedMethodInfo.value?.category
    if (cat === 'bearing') return 'primary'
    if (cat === 'gear') return 'warning'
    if (cat === 'planetary') return 'danger'
    return 'info'
  })

  // 行星箱判断
  const hasPlanetary = computed(() => {
    const d = currentDevice.value
    if (!d) return false
    const gt = d.gear_teeth
    if (!gt) return false
    // 通道级格式
    for (const [, v] of Object.entries(gt)) {
      if (typeof v === 'object' && (v?.planet_count >= 3 || (v?.sun > 0 && v?.ring > 0))) return true
    }
    if (gt.planet_count >= 3 || (gt.sun > 0 && gt.ring > 0)) return true
    return false
  })

  // 投票行数据
  const bearingVoteRows = computed(() => voteRows(result.value?.ensemble?.bearing_votes))
  const gearVoteRows = computed(() => voteRows(result.value?.ensemble?.gear_votes))

  const bestIndicatorRows = computed(() => {
    const rows = []
    appendBearingIndicators(rows, '轴承', result.value?.bearing)
    appendIndicators(rows, '齿轮', result.value?.gear?.fault_indicators)
    return rows
  })

  // D-S 融合故障概率行
  const dsFaultProbRows = computed(() => {
    const bpa = result.value?.ensemble?.ds_fusion?.fused_bpa
    const belief = result.value?.ensemble?.ds_fusion?.fused_belief
    const plaus = result.value?.ensemble?.ds_fusion?.fused_plausibility
    if (!bpa) return []
    return Object.entries(bpa)
      .filter(([k]) => k !== 'Θ')
      .map(([fault, prob]) => ({
        fault,
        bpa: prob,
        belief: belief?.[fault] ?? 0,
        plausibility: plaus?.[fault] ?? 0,
      }))
      .sort((a, b) => b.bpa - a.bpa)
  })

  // ── 全部方法模式：从 bearing_results / gear_results 提取表格数据 ──
  const isAllMode = computed(() => runMode.value === 'all')
  const hasAllResults = computed(() => result.value?.bearing_results || result.value?.gear_results)

  // 全部方法-轴承方法摘要行
  const allBearingRows = computed(() => {
    const br = result.value?.bearing_results
    if (!br || isAllMode.value === false) return []
    return Object.entries(br).map(([method, r]) => {
      if (!r || r.error) return { method, faults: [], params: r?.error || '执行失败', _error: true }
      const faults = significantBearingFaults(r).map(fault => ({
        ...fault,
        snr: fault.snr?.toFixed?.(1) ?? fault.snr,
        score: fault.score?.toFixed?.(1) ?? fault.score,
      }))
      const params = [
        r.rot_freq_hz != null ? `${r.rot_freq_hz?.toFixed?.(2) ?? r.rot_freq_hz}Hz` : '',
        r.band?.center_hz != null ? `频带${r.band.center_hz?.toFixed?.(0) ?? r.band.center_hz}Hz` : '',
        r.evaluation?.status !== 'evaluated' ? evaluationStatusText(r.evaluation?.status) : '',
        r.reason ? bearingReasonText(r.reason) : '',
      ].filter(Boolean).join(', ')
      return { method, faults, evaluationStatus: r.evaluation?.status, params: params || '-' }
    })
  })

  // 全部方法-齿轮方法摘要行
  const allGearRows = computed(() => {
    const gr = result.value?.gear_results
    if (!gr || isAllMode.value === false) return []
    return Object.entries(gr).map(([method, r]) => {
      if (!r || r.error) return { method, ser: '-', car: '-', fm0: '-', fm4: '-', sideband_count: '-', alerts: [], _error: true, _errMsg: r?.error }
      const fi = r.fault_indicators || {}
      const alerts = Object.entries(fi)
        .filter(([, v]) => v && typeof v === 'object' && (v.critical || v.warning))
        .map(([name, v]) => ({ indicator: name, level: v.critical ? 'critical' : 'warning' }))
      return {
        method,
        ser: r.is_planetary ? r.sideband_analysis?.ser?.value ?? null : r.ser != null ? Number(r.ser) : null,
        car: r.is_planetary ? r.metrics?.car?.value ?? null : r.car != null ? Number(r.car) : null,
        fm0: r.is_planetary ? r.metrics?.fm0?.value ?? null : r.fm0 != null ? Number(r.fm0) : null,
        fm4: r.is_planetary ? r.metrics?.fm4?.value ?? null : r.fm4 != null ? Number(r.fm4) : null,
        evaluationStatus: r.evaluation?.status,
        sideband_count: r.sidebands?.length ?? (r.sideband_count ?? 0),
        indicators: fi,
        alerts,
      }
    })
  })

  // 全部方法-最佳算法指标（从所有方法中提取故障指示器）
  const allBestIndicatorRows = computed(() => {
    if (isAllMode.value === false) return []
    const rows = []
    const bearingResults = result.value?.bearing_results || {}
    const gearResults = result.value?.gear_results || {}
    for (const [method, r] of Object.entries(bearingResults)) {
      if (!r || r.error) continue
      appendBearingIndicators(rows, method, r)
    }
    for (const [method, r] of Object.entries(gearResults)) {
      if (!r || r.error) continue
      appendIndicators(rows, method, r.fault_indicators)
    }
    return rows
  })

  watch(selectedDeviceId, () => {
    selectedBatchIndex.value = currentBatches.value[0]?.batch_index ?? null
    selectedChannel.value = currentChannels.value[0]?.value ?? 1
    result.value = null
  })

  watch(runMode, () => { result.value = null })

  const loadDevices = async () => {
    const res = await getAllDeviceData()
    devices.value = res.data || []
    // 从路由 query 参数预选设备/批次/通道（联动跳转）
    const qDevice = route.query.device_id
    const qBatch = route.query.batch_index
    const qChannel = route.query.channel
    if (qDevice && devices.value.length > 0) {
      selectedDeviceId.value = qDevice
      const dev = devices.value.find(d => d.device_id === qDevice)
      if (dev) {
        const batch = dev.batches?.find(b => String(b.batch_index) === String(qBatch))
        if (batch) {
          selectedBatchIndex.value = batch.batch_index
        }
        if (qChannel) {
          const ch = parseInt(qChannel)
          const count = dev.channel_count || 3
          if (ch >= 1 && ch <= count) {
            selectedChannel.value = ch
          }
        }
      }
    } else if (devices.value.length > 0 && !selectedDeviceId.value) {
      selectedDeviceId.value = devices.value[0].device_id
    }
  }

  const loadMethodInfo = async () => {
    try {
      const res = await getMethodInfo()
      methodInfoData.value = res.data || {}
    } catch (e) {
      methodInfoData.value = {}
    }
  }

  const runAnalysis = async () => {
    if (!canRun.value) return
    const comb = combFrequencies.value.trim()
      ? combFrequencies.value.split(/[,，\s]+/).filter(Boolean).map(Number) : []
    if (comb.some(value => !Number.isFinite(value) || value <= 0)) {
      ElMessage.warning('梳状频率必须是正数，单位 Hz；多个频率用逗号分隔')
      return
    }
    const methodOptions = {
      denoise: denoise.value, target_fault: targetFault.value || undefined,
      comb_frequencies_hz: comb, comb_is_stable: combIsStable.value,
      rot_freq_hz: rotFrequency.value || undefined,
    }
    loading.value = true
    result.value = null
    try {
      if (runMode.value === 'single' && selectedMethodInfo.value?.category === 'composite') {
        const body = buildCompositeRequest(selectedMethod.value, rotFrequency.value, compositeAlignment.value)
        const res = await runCompositeResearch(selectedDeviceId.value, selectedBatchIndex.value, selectedChannel.value, body)
        result.value = res.data
      } else if (runMode.value === 'single') {
        const res = await getChannelMethodAnalysis(
          selectedDeviceId.value,
          selectedBatchIndex.value,
          selectedChannel.value,
          selectedMethod.value,
          methodOptions,
        )
        result.value = res.data
      } else if (runMode.value === 'all') {
        const res = await getChannelMethodAnalysis(
          selectedDeviceId.value,
          selectedBatchIndex.value,
          selectedChannel.value,
          'all',
          methodOptions,
        )
        result.value = res.data
      } else if (runMode.value === 'ensemble') {
        const res = await getChannelResearchAnalysis(
          selectedDeviceId.value,
          selectedBatchIndex.value,
          selectedChannel.value,
          { ...methodOptions, profile: profile.value },
        )
        result.value = res.data
      }
    } catch (error) {
      ElMessage.error(formatErrorMessage(error, '诊断失败'))
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    loadDevices()
    loadMethodInfo()
  })

  // 跳转到数据查看页面，携带当前设备/批次参数
  const gotoDataView = () => {
    if (!selectedDeviceId.value || selectedBatchIndex.value == null) return
    router.push({
      path: '/data',
      query: {
        device_id: selectedDeviceId.value,
        batch_index: selectedBatchIndex.value,
      }
    })
  }

  return {
    devices,
    selectedDeviceId,
    selectedBatchIndex,
    selectedChannel,
    runMode,
    selectedMethod,
    targetFault, combFrequencies, combIsStable, rotFrequency, compositeAlignment,
    denoise,
    profile,
    loading,
    result,
    currentBatches,
    currentChannels,
    canRun,
    bearingMethodGroup,
    gearMethodGroup,
    planetaryMethodGroup,
    compositeMethodGroup,
    selectedMethodInfo,
    methodCategoryTag,
    bearingVoteRows,
    gearVoteRows,
    bestIndicatorRows,
    dsFaultProbRows,
    hasAllResults,
    allBearingRows,
    allGearRows,
    allBestIndicatorRows,
    runAnalysis,
    gotoDataView,
  }
}
