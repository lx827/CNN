/**
 * Monitor 实时监测页数据与图表逻辑
 *
 * 职责:最新振动数据拉取(推送合并串行刷新)、传感器状态、手动采集任务
 *       下发与轮询、时域/频域图表初始化与销毁、生命周期清理。
 */
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import { getRealtimeVibrationData } from '../api/monitor'
import { createRemoteRecording, getAcquisition, getAcquisitionAgents } from '../api/acquisition'
import { getDevices } from '../api/devices'
import { getWebSocketClient } from '../utils/websocket'
import { getDiagnosisView } from '../utils/diagnosisStatus'
import { formatErrorMessage } from '../utils/errorMessage'
import { baseCartesianOption, AXIS_STYLE, emptyTitle } from '../utils/chartTheme'
import { COLORS, ACQUISITION_STATUS_POLL_MS } from '../utils/constants'

const collectionStage = {
  pending: '任务已创建，等待边端领取',
  waiting_device: '等待采集设备',
  configuring: '正在配置采集设备',
  capturing: '边端正在采集',
  uploading: '正在上传采集记录',
  analyzing: '正在处理采集记录',
}

// 由语义色派生带透明度的 rgba，用于渐变面积填充，避免散落裸色值
const withAlpha = (hex, alpha) => {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

export function useMonitor() {
  const activeChannel = ref(0)
  const channels = ref([])
  const params = ref({})
  const timeDomainChart = ref(null)
  const frequencyChart = ref(null)
  let timeInstance = null
  let freqInstance = null
  let pollTimer = null
  let isUnmounted = false

  const isCollecting = ref(false)
  const collectionResult = ref(null)
  const job = ref(null)
  const lastDataSource = computed(() => channels.value[0]?.is_special ? 'special' : 'normal')
  const collectionStatus = computed(() => collectionResult.value?.text ||
    (job.value ? collectionStage[job.value.status] : isCollecting.value ? '正在创建采集任务' : ''))
  const collectionType = computed(() => collectionResult.value?.type || 'info')
  const collectionProgress = computed(() => {
    const samples = job.value?.progress?.samples_per_channel
    if (collectionResult.value || job.value?.status !== 'capturing' || !job.value.duration || samples == null) return null
    return Math.min(100, Math.floor(100 * samples / (job.value.sample_rate * job.value.duration)))
  })
  const collectionDetails = computed(() => job.value ?
    `${job.value.agent_id} · ${job.value.sample_rate.toLocaleString()} Hz · ${job.value.duration} 秒` : '')

  const devices = ref([])
  const selectedMonitorDevice = ref('')
  const agents = ref([])
  const loadingAgents = ref(false)
  const agentsError = ref('')
  const selectedCollectDevice = ref('')
  const selectedSampleRate = ref(null)
  const collectAgents = computed(() => agents.value.filter(agent => agent.source === 'dc24_tcp' && agent.state?.version >= 3)
    .map(agent => ({ ...agent, name: devices.value.find(d => d.device_id === agent.id)?.name || agent.id })))
  const selectedAgent = computed(() => collectAgents.value.find(agent => agent.id === selectedCollectDevice.value))
  const sampleRates = computed(() => selectedAgent.value?.state?.sample_rates || [])
  const collectDevice = computed(() => devices.value.find(device => device.device_id === selectedCollectDevice.value))
  const collectionDuration = computed(() => collectDevice.value?.window_seconds)
  const collectionUnavailable = computed(() => {
    if (loadingAgents.value) return '正在查询边端'
    if (agentsError.value) return agentsError.value
    if (!collectAgents.value.some(agent => agent.online)) return '没有在线的 DC24 采集边端'
    if (!selectedAgent.value?.online) return '请选择在线的 DC24 采集边端'
    if (!selectedAgent.value.state.save_directory) return '边端未配置保存目录，无法请求采集'
    if (!sampleRates.value.length) return '边端未上报支持的采样率'
    if (!sampleRates.value.includes(selectedSampleRate.value)) return '请从边端上报的档位中选择采样率'
    return ''
  })

  watch([selectedCollectDevice, sampleRates], ([deviceId, rates], [previousDeviceId]) => {
    if (deviceId === previousDeviceId && rates.includes(selectedSampleRate.value)) return
    const configured = collectDevice.value?.sample_rate
    selectedSampleRate.value = rates.includes(configured) ? configured : null
  })

  const sensors = ref([])

  // 根据通道数据动态构建传感器状态列表（只显示实际收到的振动通道）
  const buildSensors = (chList) => {
    const list = []
    chList.forEach((ch) => {
      list.push({
        name: ch.channel_name || ch.name || `振动传感器 ${ch.id || ch.channel}`,
        status: getDiagnosisView(ch).tone,
        statusText: getDiagnosisView(ch).label,
        is_offline: ch.is_offline,
        type: 'vibration'
      })
    })
    sensors.value = list
  }

  const loadDevices = async () => {
    try {
      const res = await getDevices()
      if (isUnmounted) return
      devices.value = res.data
      selectedMonitorDevice.value = devices.value[0]?.device_id || ''
    } catch (error) {
      console.error('加载设备列表失败:', error)
    }
  }

  const reloadCollectAgents = async () => {
    if (loadingAgents.value) return
    loadingAgents.value = true
    agentsError.value = ''
    try {
      const { data } = await getAcquisitionAgents()
      if (isUnmounted) return
      agents.value = data
      if (!selectedAgent.value) {
        const online = collectAgents.value.filter(agent => agent.online)
        const preferred = online.find(agent => agent.id === selectedMonitorDevice.value)
        selectedCollectDevice.value = (preferred || (online.length === 1 ? online[0] : null))?.id || ''
      }
    } catch (error) {
      agentsError.value = `无法查询采集边端：${formatErrorMessage(error)}`
    } finally {
      loadingAgents.value = false
    }
  }

  const showCollectionJob = (snapshot) => {
    job.value = snapshot
    collectionResult.value = null
    if (snapshot.status === 'completed') {
      collectionResult.value = { type: 'success', text: '采集及上传已完成' }
      const deviceId = snapshot.agent_id
      if (!devices.value.some(device => device.device_id === deviceId)) {
        devices.value = [...devices.value, { device_id: deviceId, name: deviceId }]
      }
      selectedMonitorDevice.value = deviceId
      refreshLatestData(true)
    } else if (snapshot.status === 'failed') {
      collectionResult.value = { type: 'error', text: snapshot.error ? `采集失败：${snapshot.error}` : '采集失败' }
    } else if (snapshot.status === 'cancelled') {
      collectionResult.value = { type: 'info', text: '采集已取消' }
    }
    if (collectionResult.value) isCollecting.value = false
  }

  const pollCollection = async () => {
    pollTimer = null
    try {
      const { data } = await getAcquisition(job.value.id, { silentError: true })
      if (!isUnmounted) showCollectionJob(data)
    } catch (error) {
      if (!isUnmounted) {
        collectionResult.value = { type: 'warning', text: `暂时无法查询采集状态：${formatErrorMessage(error)}` }
      }
    } finally {
      if (!isUnmounted && isCollecting.value) {
        pollTimer = setTimeout(pollCollection, ACQUISITION_STATUS_POLL_MS)
      }
    }
  }

  const requestCollect = async () => {
    if (isCollecting.value || collectionUnavailable.value) return
    isCollecting.value = true
    job.value = null
    collectionResult.value = null
    try {
      const { data } = await createRemoteRecording({
        agent_id: selectedCollectDevice.value,
        sample_rate: selectedSampleRate.value,
        duration: collectionDuration.value || undefined,
      })
      if (isUnmounted) return
      showCollectionJob(data)
      if (isCollecting.value) pollTimer = setTimeout(pollCollection, ACQUISITION_STATUS_POLL_MS)
    } catch (error) {
      if (isUnmounted) return
      collectionResult.value = { type: 'error', text: `未能创建采集任务：${formatErrorMessage(error)}` }
      isCollecting.value = false
    }
  }

  // ============ 加载最新数据 ============
  const loadLatestData = async (preferSpecial = false) => {
    try {
      const deviceId = selectedMonitorDevice.value || 'WTG-001'
      const res = await getRealtimeVibrationData(deviceId, preferSpecial)
      // 页面离开后，忽略尚未完成的请求，避免更新已销毁的图表。
      if (isUnmounted || deviceId !== (selectedMonitorDevice.value || 'WTG-001')) return
      const data = res.data
      channels.value = data.channels
      params.value = data.sensorParams
      if (activeChannel.value >= channels.value.length) activeChannel.value = 0

      // 更新传感器状态（根据数据状态）
      updateSensorStatus(data.channels)

      updateCharts()
    } catch (e) {
      console.error('加载数据失败:', e)
    }
  }

  // 切换监测设备时刷新数据
  const onMonitorDeviceChange = () => {
    refreshLatestData()
  }

  // WebSocket 实时推送
  let wsClient = null
  let latestRefreshTimer = null
  let latestRefreshPromise = null
  let latestRefreshPreferSpecial = false
  let latestRefreshPending = false

  // 推送事件可能在同一批数据到达时连续触发。合并短时间内的刷新，避免
  // sensor_update 和 diagnosis_update 各自发起一次完整的 FFT 请求。
  const refreshLatestData = (preferSpecial = false) => {
    if (isUnmounted) return Promise.resolve()
    latestRefreshPending = true
    latestRefreshPreferSpecial = latestRefreshPreferSpecial || preferSpecial
    if (latestRefreshPromise) return latestRefreshPromise

    latestRefreshPromise = (async () => {
      while (latestRefreshPending && !isUnmounted) {
        latestRefreshPending = false
        const requestPreferSpecial = latestRefreshPreferSpecial
        latestRefreshPreferSpecial = false
        await loadLatestData(requestPreferSpecial)
      }
    })().finally(() => {
      latestRefreshPromise = null
    })

    return latestRefreshPromise
  }

  const handleMonitorUpdate = (event) => {
    if (event?.device_id && event.device_id !== selectedMonitorDevice.value) return
    if (isUnmounted || latestRefreshTimer) return
    latestRefreshTimer = setTimeout(() => {
      latestRefreshTimer = null
      refreshLatestData()
    }, 100)
  }
  const setupWebSocket = () => {
    wsClient = getWebSocketClient()
    wsClient.on('sensor_update', handleMonitorUpdate)
    wsClient.on('diagnosis_update', handleMonitorUpdate)
    wsClient.connect()
  }

  const updateSensorStatus = (chList) => {
    // 诊断来自当前通道持久化结果；RMS 只用于振动图表。
    buildSensors(chList)
  }

  // ============ 图表更新 ============
  const updateCharts = () => {
    if (!channels.value[activeChannel.value]) {
      timeInstance?.setOption({ title: emptyTitle('暂无振动数据'), xAxis: { data: [] }, series: [{ data: [] }] })
      freqInstance?.setOption({ title: emptyTitle('暂无频谱数据'), xAxis: { data: [] }, series: [{ data: [] }] })
      return
    }

    const channel = channels.value[activeChannel.value]
    const timeData = channel.timeDomain
    const freqData = channel.frequency
    const fftFreq = channel.fftFreq || []
    const sampleRate = channel.sampleRate || 25600

    // 时域图：x 轴为时间（秒）
    const timeX = Array.from({ length: timeData.length }, (_, i) => (i / sampleRate).toFixed(4))
    timeInstance?.setOption({
      title: { show: false },
      xAxis: { data: timeX },
      series: [{ data: timeData }]
    })

    // 频域图：x 轴为频率 (Hz)
    const freqX = fftFreq.length > 0 ? fftFreq : Array.from({ length: freqData.length }, (_, i) => i)
    freqInstance?.setOption({
      title: { show: false },
      xAxis: { data: freqX },
      series: [{ data: freqData }]
    })
  }

  // 监听通道切换
  watch(activeChannel, () => {
    updateCharts()
  })

  const initCharts = () => {
    timeInstance = echarts.init(timeDomainChart.value)
    freqInstance = echarts.init(frequencyChart.value)

    // 坐标轴名称样式跟随主题坐标轴文字色
    const axisNameStyle = { color: AXIS_STYLE.axisLabel.color, fontSize: 12 }
    // 振动波形/频谱保持原始折线（不开 smooth），主色系列 + 轻量渐变面积
    const lineSeries = {
      type: 'line',
      data: [],
      smooth: false,
      showSymbol: false,
      lineStyle: { width: 1.5, color: COLORS.primary },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: withAlpha(COLORS.primary, 0.16) },
          { offset: 1, color: withAlpha(COLORS.primary, 0.02) }
        ])
      }
    }

    const timeOption = {
      ...baseCartesianOption(),
      grid: { left: '3%', right: '4%', bottom: '3%', top: 40, containLabel: true },
      xAxis: {
        type: 'category',
        data: [],
        boundaryGap: false,
        name: '时间 (s)',
        nameLocation: 'middle',
        nameGap: 25,
        nameTextStyle: axisNameStyle,
        ...AXIS_STYLE,
        splitLine: { show: false }
      },
      yAxis: {
        type: 'value',
        name: '振幅 (mm/s)',
        nameTextStyle: axisNameStyle,
        ...AXIS_STYLE
      },
      series: [{ ...lineSeries }]
    }

    const freqOption = {
      ...baseCartesianOption(),
      grid: { left: '3%', right: '4%', bottom: '3%', top: 40, containLabel: true },
      xAxis: {
        type: 'category',
        data: [],
        boundaryGap: false,
        name: '频率 (Hz)',
        nameLocation: 'middle',
        nameGap: 25,
        nameTextStyle: axisNameStyle,
        ...AXIS_STYLE,
        splitLine: { show: false }
      },
      yAxis: {
        type: 'value',
        name: '幅值',
        nameTextStyle: axisNameStyle,
        ...AXIS_STYLE
      },
      series: [{ ...lineSeries }]
    }

    timeInstance.setOption(timeOption)
    freqInstance.setOption(freqOption)
  }

  const handleResize = () => {
    timeInstance?.resize()
    freqInstance?.resize()
  }

  onMounted(async () => {
    // 先建立图表实例，保证首次返回的数据即可绘制默认通道。
    initCharts()
    window.addEventListener('resize', handleResize)

    await loadDevices()
    if (isUnmounted) return
    reloadCollectAgents()
    await refreshLatestData()
    if (isUnmounted) return
    setupWebSocket()
  })

  // 生命周期钩子在 setup 中同步注册，确保路由切换时执行清理。
  onUnmounted(() => {
    isUnmounted = true
    if (latestRefreshTimer) {
      clearTimeout(latestRefreshTimer)
      latestRefreshTimer = null
    }
    latestRefreshPreferSpecial = false
    latestRefreshPending = false
    if (pollTimer) {
      clearTimeout(pollTimer)
    }
    wsClient?.off('sensor_update', handleMonitorUpdate)
    wsClient?.off('diagnosis_update', handleMonitorUpdate)
    wsClient?.close()
    timeInstance?.dispose()
    freqInstance?.dispose()
    window.removeEventListener('resize', handleResize)
  })

  return {
    activeChannel,
    channels,
    params,
    sensors,
    timeDomainChart,
    frequencyChart,
    isCollecting,
    collectionStatus,
    collectionType,
    collectionProgress,
    collectionDetails,
    collectionUnavailable,
    collectionDuration,
    lastDataSource,
    devices,
    collectAgents,
    loadingAgents,
    selectedCollectDevice,
    selectedSampleRate,
    sampleRates,
    selectedMonitorDevice,
    reloadCollectAgents,
    requestCollect,
    onMonitorDeviceChange,
  }
}
