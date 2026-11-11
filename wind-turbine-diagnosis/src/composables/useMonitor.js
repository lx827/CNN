/**
 * Monitor 实时监测页数据与图表逻辑
 *
 * 职责:最新振动数据拉取(推送合并串行刷新)、传感器状态、手动采集任务
 *       下发与轮询、时域/频域图表初始化与销毁、生命周期清理。
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import { getRealtimeVibrationData } from '../api/monitor'
import { requestCollection, getTaskStatus } from '../api/system'
import { getDevices } from '../api/devices'
import { getWebSocketClient } from '../utils/websocket'
import { ElMessage } from 'element-plus'
import { getDiagnosisView } from '../utils/diagnosisStatus'

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

  // 采集状态
  const isCollecting = ref(false)
  const collectionStatus = ref('')
  const collectionProgress = ref(0)
  const currentTaskId = ref(null)
  const lastDataSource = ref('normal') // 'normal' | 'special'

  // 设备选择（采集用）
  const collectDevices = ref([])
  const selectedCollectDevice = ref('')

  // 设备选择（监测显示用）
  const selectedMonitorDevice = ref('')

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

  // ============ 请求采集 ============
  // 加载设备列表（用于采集选择）
  const loadCollectDevices = async () => {
    try {
      const res = await getDevices()
      if (isUnmounted) return
      collectDevices.value = res.data || []
      if (collectDevices.value.length > 0) {
        if (!selectedCollectDevice.value) {
          selectedCollectDevice.value = collectDevices.value[0].device_id
        }
        if (!selectedMonitorDevice.value) {
          selectedMonitorDevice.value = collectDevices.value[0].device_id
        }
      }
    } catch (e) {
      console.error('加载设备列表失败:', e)
    }
  }

  const requestCollect = async () => {
    if (isCollecting.value) return
    if (!selectedCollectDevice.value) {
      ElMessage.warning('请先选择设备')
      return
    }

    try {
      isCollecting.value = true
      collectionStatus.value = '正在创建采集任务...'
      collectionProgress.value = 10
      currentTaskId.value = null

      // 1. 向云端发送采集请求
      const res = await requestCollection(selectedCollectDevice.value)
      if (isUnmounted) return
      const taskData = res.data

      if (!taskData) {
        throw new Error('创建任务失败')
      }

      currentTaskId.value = taskData.task_id
      collectionStatus.value = '任务已创建，等待边端响应...'
      collectionProgress.value = 25

      // 2. 开始轮询任务状态
      startPolling(taskData.task_id)

      ElMessage.success('采集任务已下发，等待边端执行')
    } catch (e) {
      console.error('请求采集失败:', e)
      collectionStatus.value = '创建任务失败'
      collectionProgress.value = 0
      isCollecting.value = false
      ElMessage.error('创建采集任务失败')
    }
  }

  // ============ 轮询任务状态 ============
  const startPolling = (taskId) => {
    if (pollTimer) clearTimeout(pollTimer)
    let pollCount = 0
    const maxPolls = 60  // 最多轮询60次（约2分钟）

    const doPoll = async () => {
      if (isUnmounted) return
      try {
        pollCount++
        const res = await getTaskStatus(taskId)
        if (isUnmounted) return
        const task = res.data

        if (!task) {
          throw new Error('任务不存在')
        }

        if (task.status === 'pending') {
          collectionStatus.value = `等待边端响应... (${pollCount}s)`
          collectionProgress.value = 25 + Math.min(pollCount, 20)
        } else if (task.status === 'processing') {
          collectionStatus.value = `边端采集中... (${pollCount}s)`
          collectionProgress.value = 50 + Math.min(pollCount, 30)
        } else if (task.status === 'completed') {
          collectionStatus.value = '采集完成，正在加载数据...'
          collectionProgress.value = 90
          // 任务完成，刷新数据
          await refreshLatestData(true) // true = 优先特殊数据
          if (isUnmounted) return
          collectionStatus.value = '采集完成！'
          collectionProgress.value = 100
          isCollecting.value = false
          lastDataSource.value = 'special'
          clearTimeout(pollTimer)
          pollTimer = null
          ElMessage.success('特殊采集完成，数据已加载')
          return
        } else if (task.status === 'failed') {
          throw new Error(task.error_message || '采集失败')
        }

        if (pollCount >= maxPolls) {
          throw new Error('采集超时，请检查边端是否在线')
        }
      } catch (e) {
        if (isUnmounted) return
        console.error('轮询失败:', e)
        collectionStatus.value = e.message || '采集异常'
        collectionProgress.value = 0
        isCollecting.value = false
        clearTimeout(pollTimer)
        pollTimer = null
        ElMessage.error(e.message || '采集异常')
      } finally {
        // 上轮完成后再等待 2 秒，慢请求不会与下一轮重叠。
        if (!isUnmounted && isCollecting.value) pollTimer = setTimeout(doPoll, 2000)
      }
    }

    // 立即执行一次，后续由完成回调调度。
    doPoll()
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
      timeInstance?.setOption({ xAxis: { data: [] }, series: [{ data: [] }] })
      freqInstance?.setOption({ xAxis: { data: [] }, series: [{ data: [] }] })
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
      xAxis: { data: timeX },
      series: [{ data: timeData }]
    })

    // 频域图：x 轴为频率 (Hz)
    const freqX = fftFreq.length > 0 ? fftFreq : Array.from({ length: freqData.length }, (_, i) => i)
    freqInstance?.setOption({
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

    const timeOption = {
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        data: [],
        boundaryGap: false,
        name: '时间 (s)',
        nameLocation: 'middle',
        nameGap: 25
      },
      yAxis: {
        type: 'value',
        name: '振幅 (mm/s)'
      },
      series: [
        {
          type: 'line',
          data: [],
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.5, color: '#165DFF' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(22, 93, 255, 0.3)' },
              { offset: 1, color: 'rgba(22, 93, 255, 0.05)' }
            ])
          }
        }
      ]
    }

    const freqOption = {
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        data: [],
        boundaryGap: false,
        name: '频率 (Hz)',
        nameLocation: 'middle',
        nameGap: 25
      },
      yAxis: {
        type: 'value',
        name: '幅值'
      },
      series: [
        {
          type: 'line',
          data: [],
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.5, color: '#52C41A' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(82, 196, 26, 0.3)' },
              { offset: 1, color: 'rgba(82, 196, 26, 0.05)' }
            ])
          }
        }
      ]
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

    await loadCollectDevices()
    if (isUnmounted) return
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
    collectionProgress,
    lastDataSource,
    collectDevices,
    selectedCollectDevice,
    selectedMonitorDevice,
    requestCollect,
    startPolling,
    onMonitorDeviceChange,
  }
}
