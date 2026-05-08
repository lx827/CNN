<template>
  <div class="monitor">
    <!-- 传感器状态和运行参数 -->
    <el-row :gutter="20" class="sensor-row">
      <el-col :xs="24" :md="16">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>传感器状态</span>
              <div class="header-actions">
                <el-tag v-if="lastDataSource === 'special'" type="danger" effect="dark" class="special-tag">
                  <el-icon><Star-Filled /></el-icon> 特殊采集
                </el-tag>
                <el-select v-model="selectedCollectDevice" placeholder="选择设备" style="width: 160px" size="default">
                  <el-option
                    v-for="d in collectDevices"
                    :key="d.device_id"
                    :label="d.name"
                    :value="d.device_id"
                  />
                </el-select>
                <el-button
                  type="primary"
                  :loading="isCollecting"
                  :disabled="isCollecting || !selectedCollectDevice"
                  @click="requestCollect"
                >
                  <el-icon v-if="!isCollecting"><Video-Play /></el-icon>
                  {{ isCollecting ? collectionStatus : '请求采集' }}
                </el-button>
              </div>
            </div>
          </template>
          <el-row :gutter="20">
            <el-col :span="8" v-for="(sensor, index) in sensors" :key="index">
              <div class="sensor-item">
                <div class="indicator" :class="sensor.status"></div>
                <div class="sensor-info">
                  <div class="sensor-name">{{ sensor.name }}</div>
                  <div class="sensor-status">{{ sensor.statusText }}</div>
                </div>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="8">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>运行参数</span>
            </div>
          </template>
          <div class="params">
            <div class="param-item">
              <div class="param-label">转速</div>
              <div class="param-value">{{ params.rpm?.toFixed(1) || 0 }} <span class="unit">RPM</span></div>
            </div>
            <div class="param-item">
              <div class="param-label">温度</div>
              <div class="param-value">{{ params.temperature?.toFixed(1) || 0 }} <span class="unit">°C</span></div>
            </div>
            <div class="param-item">
              <div class="param-label">负载</div>
              <div class="param-value">{{ params.load?.toFixed(1) || 0 }} <span class="unit">%</span></div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 采集进度提示 -->
    <el-row v-if="isCollecting" :gutter="20" class="progress-row">
      <el-col :span="24">
        <el-alert
          :title="collectionStatus"
          type="info"
          :closable="false"
          show-icon
        >
          <template #default>
            <div class="progress-detail">
              <el-progress :percentage="collectionProgress" :stroke-width="8" />
              <span class="progress-hint">边端正在按 25600Hz 采集 10s 数据...</span>
            </div>
          </template>
        </el-alert>
      </el-col>
    </el-row>

    <!-- 振动信号图表 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>振动信号时域波形</span>
              <el-select v-model="activeChannel" style="width: 220px">
                <el-option
                  v-for="(channel, index) in channels"
                  :key="index"
                  :label="channel.name"
                  :value="index"
                />
              </el-select>
            </div>
          </template>
          <div ref="timeDomainChart" class="chart"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="chart-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>频域谱图</span>
              <el-tag v-if="lastDataSource === 'special'" type="danger" size="small" effect="plain">特殊采集数据</el-tag>
            </div>
          </template>
          <div ref="frequencyChart" class="chart"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import { getRealtimeVibrationData, requestCollection, getTaskStatus, getDevices } from '../api'
import { getWebSocketClient } from '../utils/websocket'
import { ElMessage } from 'element-plus'

const activeChannel = ref(0)
const channels = ref([])
const params = ref({})
const timeDomainChart = ref(null)
const frequencyChart = ref(null)
let timeInstance = null
let freqInstance = null
let pollTimer = null

// 采集状态
const isCollecting = ref(false)
const collectionStatus = ref('')
const collectionProgress = ref(0)
const currentTaskId = ref(null)
const lastDataSource = ref('normal') // 'normal' | 'special'

// 设备选择（采集用）
const collectDevices = ref([])
const selectedCollectDevice = ref('')

const sensors = ref([])

// 根据通道数据动态构建传感器状态列表
const buildSensors = (chList) => {
  const list = []
  // 振动通道
  chList.forEach((ch) => {
    list.push({
      name: ch.channel_name || ch.name || `振动传感器 ${ch.id || ch.channel}`,
      status: 'normal',
      statusText: '正常',
      type: 'vibration'
    })
  })
  // 固定运行参数传感器
  list.push(
    { name: '温度传感器', status: 'normal', statusText: '正常', type: 'param' },
    { name: '转速传感器', status: 'normal', statusText: '正常', type: 'param' },
    { name: '压力传感器', status: 'normal', statusText: '正常', type: 'param' }
  )
  sensors.value = list
}

// ============ 请求采集 ============
// 加载设备列表（用于采集选择）
const loadCollectDevices = async () => {
  try {
    const res = await getDevices()
    collectDevices.value = res.data || []
    if (collectDevices.value.length > 0 && !selectedCollectDevice.value) {
      selectedCollectDevice.value = collectDevices.value[0].device_id
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
  let pollCount = 0
  const maxPolls = 60  // 最多轮询60次（约2分钟）

  const doPoll = async () => {
    try {
      pollCount++
      const res = await getTaskStatus(taskId)
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
        await loadLatestData(true) // true = 优先特殊数据
        collectionStatus.value = '采集完成！'
        collectionProgress.value = 100
        isCollecting.value = false
        lastDataSource.value = 'special'
        clearInterval(pollTimer)
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
      console.error('轮询失败:', e)
      collectionStatus.value = e.message || '采集异常'
      collectionProgress.value = 0
      isCollecting.value = false
      clearInterval(pollTimer)
      pollTimer = null
      ElMessage.error(e.message || '采集异常')
    }
  }

  // 立即执行一次，然后每2秒轮询
  doPoll()
  pollTimer = setInterval(doPoll, 2000)
}

// ============ 加载最新数据 ============
const loadLatestData = async (preferSpecial = false) => {
  try {
    const res = await getRealtimeVibrationData(preferSpecial)
    const data = res.data
    channels.value = data.channels
    params.value = data.sensorParams

    // 更新传感器状态（根据数据状态）
    updateSensorStatus(data.channels)

    updateCharts()
  } catch (e) {
    console.error('加载数据失败:', e)
  }
}

// WebSocket 实时推送
let wsClient = null
const setupWebSocket = () => {
  wsClient = getWebSocketClient()
  wsClient.on('sensor_update', () => {
    loadLatestData()
  })
  wsClient.on('diagnosis_update', () => {
    loadLatestData()
  })
  wsClient.connect()
}

const updateSensorStatus = (chList) => {
  // 根据通道数据更新传感器状态显示
  // 先重建传感器列表（适应不同通道数）
  buildSensors(chList)
  // 更新振动通道状态
  chList.forEach((ch, idx) => {
    if (sensors.value[idx]) {
      const rms = ch.rms || 0
      if (rms > 5) {
        sensors.value[idx].status = 'danger'
        sensors.value[idx].statusText = '异常'
      } else if (rms > 2) {
        sensors.value[idx].status = 'warning'
        sensors.value[idx].statusText = '警告'
      } else {
        sensors.value[idx].status = 'normal'
        sensors.value[idx].statusText = '正常'
      }
    }
  })
}

// ============ 图表更新 ============
const updateCharts = () => {
  if (!channels.value[activeChannel.value]) return

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

onMounted(async () => {
  await loadCollectDevices()
  await loadLatestData()
  initCharts()
  setupWebSocket()

  window.addEventListener('resize', () => {
    timeInstance?.resize()
    freqInstance?.resize()
  })
})

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
  }
  wsClient?.close()
  timeInstance?.dispose()
  freqInstance?.dispose()
  window.removeEventListener('resize', () => {})
})
</script>

<style scoped>
.monitor {
  padding: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 16px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.special-tag {
  font-weight: bold;
}

.sensor-row {
  margin-bottom: 20px;
}

.progress-row {
  margin-bottom: 20px;
}

.progress-detail {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.progress-hint {
  font-size: 12px;
  color: #999;
}

.chart-row {
  margin-bottom: 20px;
}

.sensor-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  margin-bottom: 12px;
}

.indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #52C41A;
  box-shadow: 0 0 8px rgba(82, 196, 26, 0.5);
}

.indicator.warning {
  background: #FAAD14;
  box-shadow: 0 0 8px rgba(250, 173, 14, 0.5);
}

.indicator.danger {
  background: #F5222D;
  box-shadow: 0 0 8px rgba(245, 34, 45, 0.5);
}

.sensor-info {
  flex: 1;
}

.sensor-name {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

.sensor-status {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}

.params {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.param-item {
  text-align: center;
  padding: 16px;
  background: linear-gradient(135deg, #165DFF15, #0E42D215);
  border-radius: 8px;
}

.param-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.param-value {
  font-size: 28px;
  font-weight: bold;
  color: #165DFF;
}

.unit {
  font-size: 14px;
  color: #999;
}

.chart {
  height: 300px;
  width: 100%;
}
</style>
