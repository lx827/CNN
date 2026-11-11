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
import { formatErrorMessage } from '../utils/errorMessage'

export const runModeOptions = [
  { label: '单方法', value: 'single' },
  { label: '全部方法', value: 'all' },
  { label: '集成诊断', value: 'ensemble' },
]

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
    runAnalysis,
    gotoDataView,
  }
}
