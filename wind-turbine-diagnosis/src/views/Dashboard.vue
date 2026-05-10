<template>
  <div class="dashboard">
    <!-- 告警统计卡片 -->
    <el-row :gutter="16" class="summary-row">
      <el-col :xs="12" :sm="8" :md="8" :lg="4">
        <el-card class="summary-card">
          <div class="card-content">
            <el-icon :size="32" color="#165DFF"><Cpu /></el-icon>
            <div class="card-info">
              <div class="label">设备总数</div>
              <div class="value">{{ devices.length }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="8" :lg="5">
        <el-card class="summary-card">
          <div class="card-content">
            <el-icon :size="32" color="#52C41A"><CircleCheck /></el-icon>
            <div class="card-info">
              <div class="label">正常运行</div>
              <div class="value" style="color: #52C41A">{{ normalCount }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="8" :lg="5">
        <el-card class="summary-card">
          <div class="card-content">
            <el-icon :size="32" color="#FAAD14"><Warning /></el-icon>
            <div class="card-info">
              <div class="label">预警设备</div>
              <div class="value" style="color: #FAAD14">{{ warningCount }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="8" :lg="5">
        <el-card class="summary-card">
          <div class="card-content">
            <el-icon :size="32" color="#F5222D"><Delete /></el-icon>
            <div class="card-info">
              <div class="label">故障设备</div>
              <div class="value" style="color: #F5222D">{{ faultCount }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="8" :lg="5">
        <el-card class="summary-card">
          <div class="card-content">
            <el-icon :size="32" color="#909399"><Warning /></el-icon>
            <div class="card-info">
              <div class="label">离线设备</div>
              <div class="value" style="color: #909399">{{ offlineCount }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 设备健康度卡片列表 -->
    <el-row :gutter="16" class="device-cards-row">
      <el-col
        :xs="24" :sm="12" :md="8" :lg="6"
        v-for="dev in devices"
        :key="dev.deviceId"
      >
        <el-card
          class="device-card"
          :class="{ active: selectedDevice?.deviceId === dev.deviceId, offline: dev.status === 'offline' }"
          shadow="hover"
          @click="selectDevice(dev)"
        >
          <div class="device-header">
            <div class="device-id">{{ dev.deviceId }}</div>
            <el-tag :type="getStatusType(dev.status)" size="small" effect="dark">
              {{ getStatusText(dev.status) }}
            </el-tag>
          </div>
          <div class="device-name">{{ dev.deviceName }}</div>
          <div class="device-location">{{ dev.location }}</div>
          <div v-if="dev.status === 'offline'" class="offline-hint">
            <el-icon><Warning /></el-icon> 已离线
          </div>

          <div class="health-section">
            <div class="health-label">健康度</div>
            <div v-if="dev.status === 'offline'" class="offline-health">
              <el-icon><Warning /></el-icon> 离线，暂无数据
            </div>
            <el-progress
              v-else
              :percentage="dev.healthScore || 0"
              :color="getHealthColor(dev.healthScore || 0)"
              :stroke-width="12"
              :format="(p) => p"
            />
          </div>

          <div class="device-footer">
            <span><el-icon><Clock /></el-icon> {{ dev.runHours }} h</span>
            <span v-if="dev.status === 'fault' || dev.status === 'warning'" class="fault-hint">
              <el-icon><Warning /></el-icon> 需关注
            </span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 选中设备的详细图表 -->
    <template v-if="selectedDevice">
      <el-row :gutter="20" class="charts-row">
        <el-col :xs="24" :md="12">
          <el-card>
            <template #header>
              <div class="card-header">
                <span>{{ selectedDevice.deviceName }} — 健康度仪表盘</span>
              </div>
            </template>
            <div ref="gaugeChart" class="chart"></div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card>
            <template #header>
              <div class="card-header">
                <span>{{ selectedDevice.deviceName }} — 故障类型分布</span>
              </div>
            </template>
            <div ref="pieChart" class="chart"></div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 部件状态表 -->
      <el-row>
        <el-col :span="24">
          <el-card>
            <template #header>
              <div class="card-header">
                <span>{{ selectedDevice.deviceName }} — 部件状态详情</span>
              </div>
            </template>
            <el-table :data="selectedDevice.components || []" stripe>
              <el-table-column prop="name" label="部件名称" />
              <el-table-column label="状态" width="120">
                <template #default="{ row }">
                  <el-tag :type="getStatusType(row.status)">
                    {{ getStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="健康度" width="300">
                <template #default="{ row }">
                  <span v-if="row.status === 'offline'" class="offline-health">
                    <el-icon><Warning /></el-icon> 离线，暂无数据
                  </span>
                  <el-progress
                    v-else
                    :percentage="row.health || 0"
                    :color="getHealthColor(row.health || 0)"
                    :stroke-width="18"
                  />
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getDeviceInfo, getStatistics } from '../api'

const devices = ref([])
const selectedDevice = ref(null)
const alarmStats = ref({})

const gaugeChart = ref(null)
const pieChart = ref(null)
let gaugeInstance = null
let pieInstance = null

const normalCount = ref(0)
const warningCount = ref(0)
const faultCount = ref(0)
const offlineCount = ref(0)

const getStatusType = (status) => {
  const map = { normal: 'success', warning: 'warning', fault: 'danger', offline: 'info' }
  return map[status] || 'info'
}

const getStatusText = (status) => {
  const map = { normal: '正常', warning: '预警', fault: '故障', offline: '离线' }
  return map[status] || '未知'
}

const getHealthColor = (health) => {
  if (health >= 85) return '#52C41A'
  if (health >= 60) return '#FAAD14'
  return '#F5222D'
}

const loadData = async () => {
  const res = await getDeviceInfo()
  const data = res.data
  devices.value = data.devices || []
  alarmStats.value = data.alarmStats || {}

  // 统计各状态设备数量
  normalCount.value = devices.value.filter(d => d.status === 'normal').length
  warningCount.value = devices.value.filter(d => d.status === 'warning').length
  faultCount.value = devices.value.filter(d => d.status === 'fault').length
  offlineCount.value = devices.value.filter(d => d.status === 'offline').length

  // 默认选中第一个设备（如果有）
  if (devices.value.length > 0 && !selectedDevice.value) {
    selectedDevice.value = devices.value[0]
  }
}

const selectDevice = (dev) => {
  selectedDevice.value = dev
}

const initGaugeChart = () => {
  if (!gaugeChart.value) return
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
        axisTick: { show: true, length: 8, lineStyle: { color: '#999', width: 1 } },
        splitLine: { length: 16, lineStyle: { width: 2, color: '#999' } },
        axisLabel: {
          show: true,
          distance: -10,
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

  if (diag && diag.fault_probabilities) {
    const probs = diag.fault_probabilities
    pieData = Object.entries(probs)
      .filter(([name]) => name !== '正常运行')
      .map(([name, value]) => ({ name, value: Math.round(value * 100) }))
      .filter(item => item.value > 0)
  }

  // 如果没有诊断数据，用静态模拟
  if (pieData.length === 0) {
    const res = await getStatistics()
    const faultTypeMap = {
      gear_wear: '齿轮磨损',
      bearing_outer_race: '轴承外圈故障',
      bearing_inner_race: '轴承内圈故障',
      gear_broken: '齿轮断齿',
      bearing_ball: '轴承滚动体故障'
    }
    pieData = (res.data?.faultDistribution || []).map(item => ({
      name: faultTypeMap[item.name] || item.name,
      value: item.value
    }))
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
  initGaugeChart()
  initPieChart()
})

onMounted(async () => {
  await loadData()
  await nextTick()
  initGaugeChart()
  initPieChart()

  window.addEventListener('resize', () => {
    gaugeInstance?.resize()
    pieInstance?.resize()
  })
})

onUnmounted(() => {
  gaugeInstance?.dispose()
  pieInstance?.dispose()
  window.removeEventListener('resize', () => {})
})
</script>

<style scoped>
.dashboard {
  padding: 0;
}

.summary-row {
  margin-bottom: 20px;
}

.summary-card {
  border-radius: 8px;
  transition: all 0.3s;
}

.summary-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
}

.card-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.card-info {
  flex: 1;
}

.card-info .label {
  font-size: 13px;
  color: #666;
  margin-bottom: 6px;
}

.card-info .value {
  font-size: 28px;
  font-weight: bold;
  color: #333;
}

.device-cards-row {
  margin-bottom: 20px;
}

.device-card {
  cursor: pointer;
  border-radius: 10px;
  transition: all 0.3s;
  margin-bottom: 16px;
}

.device-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.12);
}

.device-card.active {
  border: 2px solid #165DFF;
  box-shadow: 0 0 0 4px rgba(22, 93, 255, 0.1);
}

.device-card.offline {
  opacity: 0.7;
  background: #f5f5f5;
}

.device-card.offline .device-name,
.device-card.offline .device-location {
  color: #999;
}

.offline-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 4px;
}

.device-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.device-id {
  font-size: 16px;
  font-weight: 700;
  color: #333;
}

.device-name {
  font-size: 14px;
  color: #555;
  margin-bottom: 4px;
}

.device-location {
  font-size: 12px;
  color: #999;
  margin-bottom: 16px;
}

.health-section {
  margin-bottom: 12px;
}

.health-label {
  font-size: 12px;
  color: #666;
  margin-bottom: 6px;
}

.device-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #999;
  border-top: 1px solid #f0f0f0;
  padding-top: 10px;
}

.fault-hint {
  color: #F5222D;
  font-weight: 600;
}

.charts-row {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 16px;
}

.offline-health {
  font-size: 13px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 4px;
}

.chart {
  height: 350px;
  width: 100%;
}
</style>
