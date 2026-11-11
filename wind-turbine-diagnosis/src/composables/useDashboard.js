/**
 * Dashboard 总览页数据与图表逻辑
 *
 * 职责：设备总览拉取(推送/轮询共享串行刷新)、状态统计、选中设备管理、
 *       健康度仪表盘与故障分布图的初始化/销毁。
 */
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getDeviceInfo } from '../api/dashboard'
import { getWebSocketClient } from '../utils/websocket'
import { getDiagnosisView } from '../utils/diagnosisStatus'

export function useDashboard() {
  const devices = ref([])
  const selectedDevice = ref(null)
  const alarmStats = ref({})

  const gaugeChart = ref(null)
  const pieChart = ref(null)
  let gaugeInstance = null
  let pieInstance = null
  let isUnmounted = false
  let pollTimer = null
  let refreshPromise = null
  let refreshPending = false
  const unsubscribe = []

  const normalCount = ref(0)
  const warningCount = ref(0)
  const faultCount = ref(0)
  const offlineCount = ref(0)
  const unknownCount = ref(0)

  const fetchDashboardData = async () => {
    if (isUnmounted) return
    const res = await getDeviceInfo()
    if (isUnmounted) return
    const data = res.data
    devices.value = data.devices || []
    alarmStats.value = data.alarmStats || {}

    // 统计各状态设备数量
    normalCount.value = devices.value.filter(d => getDiagnosisView(d).tone === 'success').length
    warningCount.value = devices.value.filter(d => getDiagnosisView(d).tone === 'warning').length
    faultCount.value = devices.value.filter(d => getDiagnosisView(d).tone === 'danger').length
    unknownCount.value = devices.value.filter(d => getDiagnosisView(d).tone === 'info').length
    offlineCount.value = devices.value.filter(d => d.is_offline).length

    // 默认选中第一个设备（如果有）
    const selectedId = selectedDevice.value?.deviceId
    selectedDevice.value = devices.value.find(d => d.deviceId === selectedId) || devices.value[0] || null
  }

  // 推送和轮询共用串行刷新；请求期间的多个事件合并为一次后续查询。
  const loadData = () => {
    if (isUnmounted) return Promise.resolve()
    refreshPending = true
    if (refreshPromise) return refreshPromise
    refreshPromise = (async () => {
      while (refreshPending && !isUnmounted) {
        refreshPending = false
        try {
          await fetchDashboardData()
        } catch (error) {
          if (!refreshPending || isUnmounted) throw error
          console.error('刷新设备总览失败，继续处理待刷新事件:', error)
        }
      }
    })().finally(() => {
      refreshPromise = null
    })
    return refreshPromise
  }

  const selectDevice = (dev) => {
    selectedDevice.value = dev
  }

  const initGaugeChart = () => {
    if (isUnmounted || !gaugeChart.value) return
    if (!gaugeInstance) gaugeInstance = echarts.init(gaugeChart.value)
    const device = selectedDevice.value
    const view = getDiagnosisView(device)
    const hasScore = view.scoreText !== '-'
    gaugeInstance.setOption({
      series: [{
        type: 'gauge', min: 0, max: 100,
        axisLine: { lineStyle: { width: 24, color: [[1, '#e8e8e8']] } },
        progress: { show: hasScore, width: 24 },
        pointer: { show: hasScore },
        itemStyle: { color: view.color },
        detail: { formatter: () => view.scoreText, fontSize: 36 },
        data: hasScore ? [{ value: device.health_score, name: view.label }] : [],
      }],
      title: { show: !hasScore, text: view.label, left: 'center', top: 'center', textStyle: { color: '#909399' } },
    }, true)
  }

  const initPieChart = () => {
    if (isUnmounted || !pieChart.value) return
    if (!pieInstance) pieInstance = echarts.init(pieChart.value)
    const diagnosis = selectedDevice.value?.diagnosis
    const counts = new Map()
    for (const deduction of diagnosis?.deductions || []) {
      if (typeof deduction.weighted_amount !== 'number' || deduction.weighted_amount <= 0) continue
      counts.set(deduction.code, (counts.get(deduction.code) || 0) + deduction.weighted_amount)
    }
    const data = Array.from(counts, ([name, value]) => ({ name, value }))
    pieInstance.setOption({
      title: { show: !data.length, text: '暂无故障扣分证据', left: 'center', top: 'center', textStyle: { color: '#909399', fontSize: 16 } },
      tooltip: { trigger: 'item', formatter: '{b}: {c} 分' },
      legend: { show: !!data.length, orient: 'vertical', right: 10, top: 'center' },
      series: [{ type: 'pie', radius: ['40%', '70%'], data }],
    }, true)
  }

  // 监听选中设备变化，更新图表
  watch(selectedDevice, async () => {
    await nextTick()
    if (isUnmounted) return
    initGaugeChart()
    initPieChart()
  })

  onMounted(async () => {
    try {
      await loadData()
    } catch (error) {
      console.error('加载设备总览失败:', error)
    }
    if (isUnmounted) return
    await nextTick()
    if (isUnmounted) return
    initGaugeChart()
    initPieChart()

    // WebSocket 监听设备上线/离线事件，实时刷新仪表板
    const wsClient = getWebSocketClient()
    wsClient.connect()
    const refresh = () => loadData().catch(error => console.error('刷新设备总览失败:', error))
    unsubscribe.push(wsClient.on('device_online', refresh), wsClient.on('device_offline', refresh))

    // 定时轮询兜底：每 60 秒刷新设备状态（防止 WebSocket 断连时状态不更新）
    pollTimer = setInterval(refresh, 60000)

    window.addEventListener('resize', handleResize)
  })

  const handleResize = () => {
    gaugeInstance?.resize()
    pieInstance?.resize()
  }

  // 必须在 setup 同步注册，防止反复路由切换累积轮询和推送订阅。
  onUnmounted(() => {
    isUnmounted = true
    refreshPending = false
    unsubscribe.forEach(off => off())
    clearInterval(pollTimer)
    gaugeInstance?.dispose()
    pieInstance?.dispose()
    window.removeEventListener('resize', handleResize)
  })

  return {
    devices,
    selectedDevice,
    alarmStats,
    normalCount,
    warningCount,
    faultCount,
    offlineCount,
    unknownCount,
    gaugeChart,
    pieChart,
    loadData,
    selectDevice,
  }
}
