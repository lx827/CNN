<template>
  <div class="diagnosis">
    <!-- 诊断概要 -->
    <el-card class="summary-card">
      <template #header>
        <div class="card-header">
          <span>诊断结果概要</span>
          <el-tag :type="statusType">{{ statusText }}</el-tag>
        </div>
      </template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="诊断时间">{{ diagnosisTime }}</el-descriptions-item>
        <el-descriptions-item label="故障数量">{{ faults.length }}</el-descriptions-item>
        <el-descriptions-item label="整体状态">
          <el-tag :type="statusType">{{ statusText }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 故障详情 -->
    <el-row :gutter="20" class="fault-row" v-for="(fault, index) in faults" :key="index">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>故障 {{ index + 1 }}: {{ fault.component }}</span>
              <el-tag :type="getSeverityType(fault.severity)">
                {{ getSeverityText(fault.severity) }}
              </el-tag>
            </div>
          </template>

          <el-row :gutter="20">
            <!-- 故障信息 -->
            <el-col :xs="24" :md="8">
              <el-descriptions :column="1" border>
                <el-descriptions-item label="故障部件">{{ fault.component }}</el-descriptions-item>
                <el-descriptions-item label="故障类型">{{ getFaultTypeText(fault.faultType) }}</el-descriptions-item>
                <el-descriptions-item label="置信度">
                  <el-progress
                    :percentage="Math.round(fault.confidence * 100)"
                    :color="getConfidenceColor(fault.confidence)"
                  />
                </el-descriptions-item>
                <el-descriptions-item label="严重程度">
                  <el-tag :type="getSeverityType(fault.severity)">
                    {{ getSeverityText(fault.severity) }}
                  </el-tag>
                </el-descriptions-item>
              </el-descriptions>
              <el-alert
                :title="fault.description"
                type="warning"
                :closable="false"
                show-icon
                style="margin-top: 16px"
              />
            </el-col>

            <!-- IMF分解图 -->
            <el-col :xs="24" :md="8">
              <div class="chart-title">IMF 分解能量分布</div>
              <div :ref="el => imfCharts[index] = el" class="chart"></div>
            </el-col>

            <!-- 故障概率图 -->
            <el-col :xs="24" :md="8">
              <div class="chart-title">故障概率分布</div>
              <div :ref="el => probCharts[index] = el" class="chart"></div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getFaultDiagnosisResult } from '../api'

const faults = ref([])
const diagnosisTime = ref('')
const imfCharts = ref([])
const probCharts = ref([])
const chartInstances = []

const statusText = '发现预警'
const statusType = 'warning'

const getSeverityType = (severity) => {
  const map = { low: 'info', medium: 'warning', high: 'danger' }
  return map[severity] || 'info'
}

const getSeverityText = (severity) => {
  const map = { low: '轻度', medium: '中度', high: '重度' }
  return map[severity] || '未知'
}

const getFaultTypeText = (type) => {
  const map = {
    inner_race: '轴承内圈故障',
    outer_race: '轴承外圈故障',
    ball: '轴承滚动体故障',
    broken: '齿轮断齿',
    missing: '齿轮缺齿',
    rootcrack: '齿轮齿根裂纹',
    wear: '齿轮磨损',
    normal: '正常'
  }
  return map[type] || type
}

const getConfidenceColor = (confidence) => {
  if (confidence >= 0.8) return '#F5222D'
  if (confidence >= 0.6) return '#FAAD14'
  return '#52C41A'
}

const initIMFChart = (index, imfData) => {
  const chart = echarts.init(imfCharts.value[index])
  chartInstances.push(chart)

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: imfData.map(item => item.name)
    },
    yAxis: {
      type: 'value',
      name: '能量 (%)'
    },
    series: [
      {
        type: 'bar',
        data: imfData.map(item => ({
          value: item.energy,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#165DFF' },
              { offset: 1, color: '#0E42D2' }
            ])
          }
        })),
        barWidth: '60%'
      }
    ]
  }
  chart.setOption(option)
}

const initProbChart = (index, probabilities) => {
  const chart = echarts.init(probCharts.value[index])
  chartInstances.push(chart)

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: '{b}: {c}%'
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'value',
      max: 1,
      axisLabel: { formatter: (v) => `${(v * 100).toFixed(0)}%` }
    },
    yAxis: {
      type: 'category',
      data: probabilities.map(item => item.type).reverse()
    },
    series: [
      {
        type: 'bar',
        data: probabilities.map(item => ({
          value: item.probability,
          itemStyle: {
            color: item.probability > 0.7
              ? '#F5222D'
              : item.probability > 0.5
                ? '#FAAD14'
                : '#52C41A'
          }
        })).reverse(),
        barWidth: '60%',
        label: {
          show: true,
          position: 'right',
          formatter: (params) => `${(params.value * 100).toFixed(1)}%`
        }
      }
    ]
  }
  chart.setOption(option)
}

onMounted(async () => {
  const res = await getFaultDiagnosisResult()
  diagnosisTime.value = res.data.diagnosisTime
  faults.value = res.data.faults

  // 关键：等DOM更新完成后，再初始化图表
  await nextTick()

  // 初始化所有图表
  faults.value.forEach((fault, index) => {
    initIMFChart(index, fault.imfComponents)
    initProbChart(index, fault.probabilities)
  })

  window.addEventListener('resize', () => {
    chartInstances.forEach(chart => chart.resize())
  })
})
</script>

<style scoped>
.diagnosis {
  padding: 0;
}

.summary-card {
  margin-bottom: 20px;
}

.fault-row {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 16px;
}

.chart-title {
  font-size: 14px;
  color: #666;
  margin-bottom: 12px;
  font-weight: 500;
}

.chart {
  height: 280px;
  width: 100%;
}
</style>
