<template>
  <div class="monitor">
    <!-- 传感器状态和运行参数 -->
    <el-row :gutter="20" class="sensor-row">
      <el-col :xs="24" :md="16">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>传感器状态</span>
              <el-button type="primary" @click="toggleMonitor">
                {{ isMonitoring ? '暂停监测' : '开始监测' }}
              </el-button>
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

    <!-- 振动信号图表 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>振动信号时域波形</span>
              <el-select v-model="activeChannel" style="width: 200px">
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
            </div>
          </template>
          <div ref="frequencyChart" class="chart"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { getRealtimeVibrationData } from '../api'

const isMonitoring = ref(true)
const activeChannel = ref(0)
const channels = ref([])
const params = ref({})
const timeDomainChart = ref(null)
const frequencyChart = ref(null)
let timeInstance = null
let freqInstance = null
let timer = null

const sensors = ref([
  { name: '振动传感器 1', status: 'normal', statusText: '正常' },
  { name: '振动传感器 2', status: 'normal', statusText: '正常' },
  { name: '振动传感器 3', status: 'normal', statusText: '正常' },
  { name: '温度传感器', status: 'normal', statusText: '正常' },
  { name: '转速传感器', status: 'normal', statusText: '正常' },
  { name: '压力传感器', status: 'normal', statusText: '正常' }
])

const toggleMonitor = () => {
  isMonitoring.value = !isMonitoring.value
  if (isMonitoring.value) {
    startUpdate()
  } else {
    stopUpdate()
  }
}

const startUpdate = () => {
  timer = setInterval(async () => {
    await updateData()
  }, 2000)
}

const stopUpdate = () => {
  clearInterval(timer)
  timer = null
}

const updateData = async () => {
  const res = await getRealtimeVibrationData()
  channels.value = res.data.channels
  params.value = res.data.sensorParams

  updateCharts()
}

const updateCharts = () => {
  if (!channels.value[activeChannel.value]) return

  const channel = channels.value[activeChannel.value]
  const timeData = channel.timeDomain
  const freqData = channel.frequency
  const xData = Array.from({ length: timeData.length }, (_, i) => i)

  timeInstance?.setOption({
    xAxis: { data: xData },
    series: [{ data: timeData }]
  })

  freqInstance?.setOption({
    xAxis: { data: xData },
    series: [{ data: freqData }]
  })
}

const initCharts = () => {
  timeInstance = echarts.init(timeDomainChart.value)
  freqInstance = echarts.init(frequencyChart.value)

  const timeOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: [],
      boundaryGap: false
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
      boundaryGap: false
    },
    yAxis: {
      type: 'value',
      name: '频率 (Hz)'
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
  await updateData()
  initCharts()

  window.addEventListener('resize', () => {
    timeInstance?.resize()
    freqInstance?.resize()
  })

  startUpdate()
})

onUnmounted(() => {
  stopUpdate()
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

.sensor-row {
  margin-bottom: 20px;
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
