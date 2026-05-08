<template>
  <div class="diagnosis">
    <!-- 诊断概要 -->
    <el-card class="summary-card">
      <template #header>
        <div class="card-header">
          <div style="display: flex; align-items: center; gap: 16px;">
            <span>故障诊断</span>
            <el-select v-model="selectedDeviceId" size="small" style="width: 160px" @change="loadDiagnosis">
              <el-option
                v-for="dev in deviceList"
                :key="dev.device_id"
                :label="dev.name"
                :value="dev.device_id"
              />
            </el-select>
          </div>
          <el-tag :type="statusType">{{ statusText }}</el-tag>
        </div>
      </template>
      <el-descriptions :column="4" border>
        <el-descriptions-item label="诊断时间">{{ diagnosisTime }}</el-descriptions-item>
        <el-descriptions-item label="故障部件数">{{ componentList.filter(c => c.healthScore < 80).length }}</el-descriptions-item>
        <el-descriptions-item label="整体状态">
          <el-tag :type="statusType">{{ statusText }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="整体健康度">
          <el-progress
            :percentage="healthScore"
            :color="healthScore > 80 ? '#52C41A' : healthScore > 60 ? '#FAAD14' : '#F5222D'"
            style="width: 120px"
          />
        </el-descriptions-item>
        <el-descriptions-item label="分析批次">
          <el-tag size="small" type="info">批次 #{{ batchIndex }}</el-tag>
          <el-button
            v-if="batchIndex > 0"
            link
            type="primary"
            size="small"
            style="margin-left: 8px"
            @click="goToDataView"
          >
            <el-icon><Link /></el-icon> 查看原始数据
          </el-button>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 部件诊断详情 -->
    <el-row :gutter="20" class="component-row" v-for="comp in componentList" :key="comp.id">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>{{ comp.name }} — {{ comp.channelName }}</span>
              <el-tag :type="comp.healthScore > 80 ? 'success' : comp.healthScore > 60 ? 'warning' : 'danger'">
                健康度 {{ comp.healthScore }}%
              </el-tag>
            </div>
          </template>

          <el-row :gutter="20">
            <!-- 部件信息 -->
            <el-col :xs="24" :md="6">
              <el-descriptions :column="1" border>
                <el-descriptions-item label="关联通道">{{ comp.channelName }}</el-descriptions-item>
                <el-descriptions-item label="部件类型">{{ comp.name }}</el-descriptions-item>
                <el-descriptions-item label="健康度">
                  <el-progress
                    :percentage="comp.healthScore"
                    :color="comp.healthScore > 80 ? '#52C41A' : comp.healthScore > 60 ? '#FAAD14' : '#F5222D'"
                  />
                </el-descriptions-item>
                <el-descriptions-item label="预估剩余寿命">
                  <span style="font-size: 18px; font-weight: 600; color: #165DFF;">{{ comp.rul }}</span> 小时
                </el-descriptions-item>
              </el-descriptions>
            </el-col>

            <!-- 故障概率分布图 -->
            <el-col :xs="24" :md="9">
              <div class="chart-title">故障概率分布</div>
              <div :ref="el => setChartRef('prob', comp.id, el)" class="chart"></div>
            </el-col>

            <!-- RUL 预测图 -->
            <el-col :xs="24" :md="9">
              <div class="chart-title">寿命 RUL 预测</div>
              <div :ref="el => setChartRef('rul', comp.id, el)" class="chart"></div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import * as echarts from 'echarts'
import { getFaultDiagnosisResult, getDevices } from '../api'
import { useRouter } from 'vue-router'

const diagnosisTime = ref('')
const healthScore = ref(87)
const overallStatus = ref('normal')
const batchIndex = ref(0)
const deviceList = ref([])
const selectedDeviceId = ref('WTG-001')
const componentList = ref([])
const router = useRouter()

const chartDomRefs = ref({}) // { [compId]: { prob: el, rul: el } }
const chartInstances = ref({}) // { [compId]: { prob: echarts, rul: echarts } }

const statusMap = {
  normal: { text: '正常运行', type: 'success' },
  warning: { text: '发现预警', type: 'warning' },
  critical: { text: '严重故障', type: 'danger' }
}

const statusText = computed(() => statusMap[overallStatus.value]?.text || '未知')
const statusType = computed(() => statusMap[overallStatus.value]?.type || 'info')

const setChartRef = (chartType, compId, el) => {
  if (!el) return
  if (!chartDomRefs.value[compId]) {
    chartDomRefs.value[compId] = {}
  }
  chartDomRefs.value[compId][chartType] = el
}

const clearCharts = () => {
  Object.values(chartInstances.value).forEach(({ prob, rul }) => {
    prob?.dispose()
    rul?.dispose()
  })
  chartInstances.value = {}
  chartDomRefs.value = {}
}

// 通道名称 → 部件信息映射
const getComponentInfo = (channelName) => {
  const name = (channelName || '').toLowerCase()
  if (name.includes('轴承')) {
    return { name: '轴承系统', relatedFaults: ['inner_race', 'outer_race', 'ball'] }
  }
  if (name.includes('齿轮') || name.includes('驱动')) {
    return { name: '齿轮系统', relatedFaults: ['wear', 'broken', 'missing', 'rootcrack'] }
  }
  if (name.includes('风扇')) {
    return { name: '风扇系统', relatedFaults: [] }
  }
  if (name.includes('轴')) {
    return { name: '轴系', relatedFaults: ['misalignment'] }
  }
  if (name.includes('底座') || name.includes('基础') || name.includes('松动')) {
    return { name: '底座/基础', relatedFaults: ['looseness'] }
  }
  return { name: '通用部件', relatedFaults: [] }
}

// 故障类型中文名映射
const faultNameMap = {
  wear: '齿轮磨损',
  inner_race: '轴承内圈故障',
  outer_race: '轴承外圈故障',
  ball: '轴承滚动体故障',
  broken: '齿轮断齿',
  missing: '齿轮缺齿',
  rootcrack: '齿轮齿根裂纹',
  normal: '正常运行',
  misalignment: '轴不对中',
  looseness: '基础松动'
}

// 计算 RUL（简化退化模型）
const calculateRUL = (componentHealth) => {
  const maxLife = 10000 // 假设最大寿命 10000 小时
  return Math.round((componentHealth / 100) * maxLife)
}

// 生成部件列表
const generateComponents = (deviceChannels, faultProbabilities) => {
  const probs = faultProbabilities || {}
  const components = []

  // 默认 3 个通道
  const channelCount = Object.keys(deviceChannels || {}).length || 3

  for (let i = 1; i <= channelCount; i++) {
    const chName = deviceChannels?.[String(i)] || `通道${i}`
    const compInfo = getComponentInfo(chName)

    // 过滤该部件相关的故障概率
    let relatedProbs = compInfo.relatedFaults
      .map(faultType => {
        const faultName = faultNameMap[faultType]
        return {
          type: faultType,
          name: faultName,
          probability: probs[faultName] || 0
        }
      })
      .filter(p => p.probability > 0.01)

    // 如果没有任何相关故障概率，显示正常运行
    if (relatedProbs.length === 0) {
      relatedProbs = [{ type: 'normal', name: '正常运行', probability: 0.95 }]
    } else {
      // 归一化概率
      const total = relatedProbs.reduce((sum, p) => sum + p.probability, 0)
      relatedProbs = relatedProbs.map(p => ({ ...p, probability: p.probability / total }))
    }

    // 按概率排序
    relatedProbs.sort((a, b) => b.probability - a.probability)

    // 计算部件健康度（基于最大故障概率）
    const maxProb = Math.max(...relatedProbs.map(p => p.probability))
    const componentHealth = Math.round((1 - maxProb) * 100)

    components.push({
      id: i,
      name: compInfo.name,
      channelName: chName,
      healthScore: componentHealth,
      rul: calculateRUL(componentHealth),
      probabilities: relatedProbs
    })
  }

  return components
}

// 初始化故障概率图
const initProbChart = (el, probabilities) => {
  const chart = echarts.init(el)
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const p = params[0]
        return `${p.name}: ${(p.value * 100).toFixed(1)}%`
      }
    },
    grid: { left: '3%', right: '12%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'value',
      max: 1,
      axisLabel: { formatter: (v) => `${(v * 100).toFixed(0)}%` }
    },
    yAxis: {
      type: 'category',
      data: probabilities.map(item => item.name).reverse()
    },
    series: [{
      type: 'bar',
      data: probabilities.map(item => ({
        value: item.probability,
        itemStyle: {
          color: item.probability > 0.7 ? '#F5222D'
            : item.probability > 0.4 ? '#FAAD14'
            : '#52C41A'
        }
      })).reverse(),
      barWidth: '60%',
      label: {
        show: true,
        position: 'right',
        formatter: (params) => `${(params.value * 100).toFixed(1)}%`
      }
    }]
  }
  chart.setOption(option)
  return chart
}

// 初始化 RUL 图
const initRULChart = (el, rulValue) => {
  const chart = echarts.init(el)
  const option = {
    series: [{
      type: 'gauge',
      startAngle: 180,
      endAngle: 0,
      min: 0,
      max: 10000,
      splitNumber: 5,
      axisLine: {
        lineStyle: {
          width: 12,
          color: [
            [0.3, '#F5222D'],
            [0.6, '#FAAD14'],
            [1, '#52C41A']
          ]
        }
      },
      pointer: {
        icon: 'path://M12.8,0.7l12,40.1H0.7L12.8,0.7z',
        length: '60%',
        width: 8,
        offsetCenter: [0, '-10%'],
        itemStyle: { color: 'auto' }
      },
      axisTick: { length: 10, lineStyle: { color: 'auto', width: 2 } },
      splitLine: { length: 15, lineStyle: { color: 'auto', width: 3 } },
      axisLabel: {
        color: '#666',
        fontSize: 12,
        distance: -45,
        formatter: (value) => {
          if (value === 10000) return '10000h'
          if (value === 7500) return '7500h'
          if (value === 5000) return '5000h'
          if (value === 2500) return '2500h'
          if (value === 0) return '0h'
          return ''
        }
      },
      title: { offsetCenter: [0, '18%'], fontSize: 14, color: '#666' },
      detail: {
        fontSize: 22,
        offsetCenter: [0, '50%'],
        valueAnimation: true,
        formatter: '{value} 小时',
        color: 'auto'
      },
      data: [{ value: rulValue, name: '剩余寿命' }]
    }]
  }
  chart.setOption(option)
  return chart
}

const loadDiagnosis = async () => {
  const res = await getFaultDiagnosisResult(selectedDeviceId.value)
  const d = res.data || {}
  diagnosisTime.value = d.diagnosisTime
  overallStatus.value = d.overallStatus || 'normal'
  healthScore.value = d.healthScore || 87
  batchIndex.value = d.batchIndex || 0

  // 获取当前设备的通道信息
  const currentDevice = deviceList.value.find(dev => dev.device_id === selectedDeviceId.value)
  const channelNames = currentDevice?.channel_names || {}

  // 生成部件列表
  componentList.value = generateComponents(channelNames, d.faultProbabilities)

  // 清理旧图表
  clearCharts()

  await nextTick()

  // 初始化所有图表
  componentList.value.forEach(comp => {
    const doms = chartDomRefs.value[comp.id]
    if (!doms) return

    if (doms.prob) {
      const probChart = initProbChart(doms.prob, comp.probabilities)
      if (!chartInstances.value[comp.id]) chartInstances.value[comp.id] = {}
      chartInstances.value[comp.id].prob = probChart
    }
    if (doms.rul) {
      const rulChart = initRULChart(doms.rul, comp.rul)
      if (!chartInstances.value[comp.id]) chartInstances.value[comp.id] = {}
      chartInstances.value[comp.id].rul = rulChart
    }
  })
}

onMounted(async () => {
  const devRes = await getDevices()
  deviceList.value = (devRes.data || []).map(d => ({
    device_id: d.device_id,
    name: d.name || d.device_id,
    channel_names: d.channel_names
  }))
  if (deviceList.value.length > 0 && !selectedDeviceId.value) {
    selectedDeviceId.value = deviceList.value[0].device_id
  }

  await loadDiagnosis()

  window.addEventListener('resize', () => {
    Object.values(chartInstances.value).forEach(({ prob, rul }) => {
      prob?.resize()
      rul?.resize()
    })
  })
})

const goToDataView = () => {
  router.push({
    path: '/data-view',
    query: { device_id: selectedDeviceId.value, batch_index: batchIndex.value }
  })
}

onUnmounted(() => {
  clearCharts()
})
</script>

<style scoped>
.diagnosis {
  padding: 0;
}

.summary-card {
  margin-bottom: 20px;
}

.component-row {
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
