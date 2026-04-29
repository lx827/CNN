<template>
  <div class="dashboard">
    <!-- 设备状态卡片 -->
    <el-row :gutter="20" class="status-cards">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="status-card">
          <div class="card-content">
            <el-icon :size="40" color="#165DFF"><Cpu /></el-icon>
            <div class="card-info">
              <div class="label">设备状态</div>
              <div class="value" :class="deviceInfo?.status">{{ statusText }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="status-card">
          <div class="card-content">
            <el-icon :size="40" color="#52C41A"><CircleCheck /></el-icon>
            <div class="card-info">
              <div class="label">健康度评分</div>
              <div class="value">{{ deviceInfo?.healthScore || 0 }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="status-card">
          <div class="card-content">
            <el-icon :size="40" color="#FAAD14"><Clock /></el-icon>
            <div class="card-info">
              <div class="label">运行时长</div>
              <div class="value">{{ runHours }} 小时</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="status-card">
          <div class="card-content">
            <el-icon :size="40" color="#F5222D"><Warning /></el-icon>
            <div class="card-info">
              <div class="label">告警数量</div>
              <div class="value">{{ alarmCount }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 健康度仪表盘 + 故障分布图 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :xs="24" :md="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>健康度仪表盘</span>
            </div>
          </template>
          <div ref="gaugeChart" class="chart"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>故障类型分布</span>
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
              <span>部件状态详情</span>
            </div>
          </template>
          <el-table :data="deviceInfo?.components || []" stripe>
            <el-table-column prop="name" label="部件名称" />
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="getStatusType(row.status)">
                  {{ getStatusText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="健康度" width="200">
              <template #default="{ row }">
                <el-progress
                  :percentage="row.health"
                  :color="getHealthColor(row.health)"
                  :stroke-width="18"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { getDeviceInfo, getStatistics } from '../api'

const deviceInfo = ref(null)
const alarmCount = ref(28)
const gaugeChart = ref(null)
const pieChart = ref(null)
let gaugeInstance = null
let pieInstance = null

const statusText = '运行中'
const runHours = 12560

const getStatusType = (status) => {
  const map = { normal: 'success', warning: 'warning', danger: 'danger' }
  return map[status] || 'info'
}

const getStatusText = (status) => {
  const map = { normal: '正常', warning: '预警', danger: '故障' }
  return map[status] || '未知'
}

const getHealthColor = (health) => {
  if (health >= 85) return '#52C41A'
  if (health >= 70) return '#FAAD14'
  return '#F5222D'
}

const initGaugeChart = () => {
  gaugeInstance = echarts.init(gaugeChart.value)
  const option = {
    series: [
      {
        type: 'gauge',
        startAngle: 200,
        endAngle: -20,
        min: 0,
        max: 100,
        splitNumber: 10,
        itemStyle: { color: '#165DFF' },
        progress: {
          show: true,
          width: 30
        },
        pointer: {
          show: true,
          length: '60%',
          width: 5
        },
        axisLine: {
          lineStyle: {
            width: 30,
            color: [
              [0.3, '#F5222D'],
              [0.7, '#FAAD14'],
              [1, '#52C41A']
            ]
          }
        },
        axisTick: { show: false },
        splitLine: {
          length: 15,
          lineStyle: { width: 2, color: '#999' }
        },
        detail: {
          fontSize: 40,
          offsetCenter: [0, '20%'],
          formatter: '{value}',
          color: '#165DFF',
          fontWeight: 'bold'
        },
        data: [
          {
            value: deviceInfo.value?.healthScore || 0,
            name: '健康度'
          }
        ]
      }
    ]
  }
  gaugeInstance.setOption(option)
}

const initPieChart = async () => {
  pieInstance = echarts.init(pieChart.value)
  const res = await getStatistics()
  const option = {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      right: 10,
      top: 'center'
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['35%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: { show: false },
        emphasis: {
          label: {
            show: true,
            fontSize: 16,
            fontWeight: 'bold'
          }
        },
        data: res.data.faultDistribution,
        color: ['#165DFF', '#52C41A', '#FAAD14', '#F5222D', '#722ED1']
      }
    ]
  }
  pieInstance.setOption(option)
}

onMounted(async () => {
  const res = await getDeviceInfo()
  deviceInfo.value = res.data
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

.status-cards {
  margin-bottom: 20px;
}

.status-card {
  margin-bottom: 20px;
  border-radius: 8px;
  transition: all 0.3s;
}

.status-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
}

.card-content {
  display: flex;
  align-items: center;
  gap: 20px;
}

.card-info {
  flex: 1;
}

.card-info .label {
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

.card-info .value {
  font-size: 28px;
  font-weight: bold;
  color: #333;
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

.chart {
  height: 350px;
  width: 100%;
}
</style>
