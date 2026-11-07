/**
 * Dashboard 总览页数据与图表逻辑
 *
 * 职责：设备总览拉取(推送/轮询共享串行刷新)、状态统计、选中设备管理、
 *       健康度仪表盘与故障分布图的初始化/销毁。
 * 状态映射为 Dashboard 专属口径(critical 计入故障、健康度 85/60 分档)，
 * 与 utils/status.js 的通用口径不同，不可混用。
 */
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getDeviceInfo } from '../api/dashboard'
import { getWebSocketClient } from '../utils/websocket'

export const getStatusType = (status) => {
  const map = { normal: 'success', warning: 'warning', fault: 'danger', critical: 'danger', offline: 'info' }
  return map[status] || 'info'
}

export const getStatusText = (status) => {
  const map = { normal: '正常', warning: '预警', fault: '故障', critical: '故障', offline: '离线' }
  return map[status] || '未知'
}

export const getHealthColor = (health) => {
  if (health >= 85) return '#52C41A'
  if (health >= 60) return '#FAAD14'
  return '#F5222D'
}

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

  const fetchDashboardData = async () => {
    if (isUnmounted) return
    const res = await getDeviceInfo()
    if (isUnmounted) return
    const data = res.data
    devices.value = data.devices || []
    alarmStats.value = data.alarmStats || {}

    // 统计各状态设备数量
    normalCount.value = devices.value.filter(d => d.status === 'normal').length
    warningCount.value = devices.value.filter(d => d.status === 'warning').length
    faultCount.value = devices.value.filter(d => ['fault', 'critical'].includes(d.status)).length
    offlineCount.value = devices.value.filter(d => d.status === 'offline').length

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

    const isOffline = selectedDevice.value?.status === 'offline'
    const score = selectedDevice.value?.healthScore || 0

    if (isOffline) {
      gaugeInstance.setOption({
        series: [{
          type: 'gauge',
          radius: '90%',
          startAngle: 200,
          endAngle: -20,
          min: 0,
          max: 100,
          splitNumber: 10,
          itemStyle: { color: '#d9d9d9' },
          progress: { show: true, width: 24, itemStyle: { color: '#d9d9d9' } },
          pointer: { show: false },
          axisLine: {
            lineStyle: {
              width: 24,
              color: [[1, '#e8e8e8']]
            }
          },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          detail: {
            fontSize: 28,
            offsetCenter: [0, '50%'],
            formatter: () => '离线',
            color: '#999',
            fontWeight: 'bold'
          },
          data: [{ value: 0, name: '设备离线' }]
        }]
      }, true)
      return
    }

    const option = {
      series: [
        {
          type: 'gauge',
          radius: '90%',
          startAngle: 200,
          endAngle: -20,
          min: 0,
          max: 100,
          splitNumber: 10,
          itemStyle: { color: '#165DFF' },
          progress: { show: true, width: 24 },
          pointer: { show: true, length: '60%', width: 5 },
          axisLine: {
            lineStyle: {
              width: 24,
              color: [
                [0.3, '#F5222D'],
                [0.6, '#FAAD14'],
                [1, '#52C41A']
              ]
            }
          },
          axisTick: { show: true, length: 14, lineStyle: { color: '#999', width: 1 } },
          splitLine: { length: 20, lineStyle: { width: 2, color: '#999' } },
          axisLabel: {
            show: true,
            distance: 25,
            fontSize: 13,
            color: '#666',
            formatter: (value) => Math.round(value)
          },
          detail: {
            fontSize: 36,
            offsetCenter: [0, '50%'],
            formatter: '{value}',
            color: score >= 85 ? '#52C41A' : score >= 60 ? '#FAAD14' : '#F5222D',
            fontWeight: 'bold'
          },
          data: [{ value: score, name: '健康度' }]
        }
      ]
    }
    gaugeInstance.setOption(option, true)
  }

  const initPieChart = async () => {
    if (!pieChart.value) return
    if (!pieInstance) pieInstance = echarts.init(pieChart.value)

    const isOffline = selectedDevice.value?.status === 'offline'

    // 离线设备：显示空图表 + 提示文字
    if (isOffline) {
      pieInstance.setOption({
        title: {
          text: '暂无数据',
          left: 'center',
          top: 'center',
          textStyle: { color: '#999', fontSize: 16 }
        },
        tooltip: { show: false },
        legend: { show: false },
        series: [
          {
            type: 'pie',
            radius: ['40%', '70%'],
            center: ['35%', '50%'],
            label: { show: false },
            data: [{ value: 1, name: '暂无数据', itemStyle: { color: '#e8e8e8' } }]
          }
        ]
      }, true)
      return
    }

    // 使用选中设备的诊断数据，按轴承/齿轮/其他归类聚合
    const diag = selectedDevice.value?.diagnosis
    let pieData = []

    // 有效故障类型白名单（与后端保持一致，排除已废弃的轴不对中、基础松动）
    const validFaultTypes = new Set([
      '齿轮磨损', '轴承内圈故障', '轴承外圈故障', '滚动体故障',
      '齿轮断齿', '齿轮缺齿', '齿轮齿根裂纹'
    ])

    if (diag && diag.fault_probabilities) {
      const probs = diag.fault_probabilities
      pieData = Object.entries(probs)
        .filter(([name]) => name !== '正常运行' && validFaultTypes.has(name))
        .map(([name, value]) => ({ name, value: Math.round(value * 100) }))
        .filter(item => item.value > 0)
    }

    const option = {
      title: { show: false },
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { orient: 'vertical', right: 10, top: 'center' },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          center: ['35%', '50%'],
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
          label: {
            show: true,
            formatter: '{b}\n{d}%',
            fontSize: 13,
            fontWeight: 'bold',
            color: '#333'
          },
          labelLine: {
            show: true,
            length: 15,
            length2: 20,
            lineStyle: { color: '#999', width: 1 }
          },
          emphasis: {
            label: { show: true, fontSize: 15, fontWeight: 'bold' },
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.2)'
            }
          },
          data: pieData,
          color: ['#165DFF', '#FAAD14', '#52C41A', '#F5222D']
        }
      ]
    }
    pieInstance.setOption(option, true)
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
    gaugeChart,
    pieChart,
    loadData,
    selectDevice,
    getStatusType,
    getStatusText,
    getHealthColor,
  }
}
