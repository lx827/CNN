<template>
  <div class="research-diagnosis">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="selectors">
        <el-select v-model="selectedDeviceId" placeholder="设备" filterable class="select">
          <el-option v-for="device in devices" :key="device.device_id" :label="device.device_name || device.device_id" :value="device.device_id" />
        </el-select>

        <el-select v-model="selectedBatchIndex" placeholder="批次" filterable class="select small">
          <el-option v-for="batch in currentBatches" :key="batch.batch_index" :label="`#${batch.batch_index}`" :value="batch.batch_index" />
        </el-select>

        <el-select v-model="selectedChannel" placeholder="通道" class="select small">
          <el-option v-for="ch in currentChannels" :key="ch.value" :label="ch.label" :value="ch.value" />
        </el-select>

        <el-segmented v-model="runMode" :options="runModeOptions" />

        <el-select v-if="runMode === 'single'" v-model="selectedMethod" class="select method-select" placeholder="分析方法" filterable>
          <el-option-group label="轴承诊断">
            <el-option v-for="m in bearingMethodGroup" :key="m.key" :value="m.key" :label="m.label" />
          </el-option-group>
          <el-option-group label="齿轮诊断">
            <el-option v-for="m in gearMethodGroup" :key="m.key" :value="m.key" :label="m.label" />
          </el-option-group>
          <el-option-group v-if="planetaryMethodGroup.length" label="行星箱专用">
            <el-option v-for="m in planetaryMethodGroup" :key="m.key" :value="m.key" :label="m.label" />
          </el-option-group>
        </el-select>

        <el-select v-model="denoise" class="select small">
          <el-option label="不去噪" value="none" />
          <el-option label="小波" value="wavelet" />
          <el-option label="VMD" value="vmd" />
        </el-select>

        <el-select v-if="runMode === 'ensemble'" v-model="profile" class="select small">
          <el-option label="运行级" value="runtime" />
          <el-option label="均衡" value="balanced" />
          <el-option label="全量" value="exhaustive" />
        </el-select>
      </div>

      <el-button type="primary" :loading="loading" :disabled="!canRun" @click="runAnalysis">
        <el-icon><Cpu /></el-icon>
        <span>{{ runMode === 'single' ? '运行方法' : runMode === 'ensemble' ? '集成诊断' : '运行全部' }}</span>
      </el-button>
      <el-button type="default" @click="gotoDataView">
        <el-icon><DataLine /></el-icon> 查看数据
      </el-button>
    </div>

    <!-- 方法说明提示 -->
    <div v-if="runMode === 'single' && selectedMethodInfo" class="method-desc-card">
      <el-tag :type="methodCategoryTag" size="small">{{ selectedMethodInfo.label }}</el-tag>
      <span class="method-desc-text">{{ selectedMethodInfo.description }}</span>
    </div>

    <!-- 全方法/集成诊断摘要 -->
    <div v-if="result && runMode !== 'single'" class="summary-band">
      <div class="metric">
        <span class="label">状态</span>
        <el-tag :type="statusType(result.status)" size="large">{{ statusText(result.status) }}</el-tag>
      </div>
      <div class="metric"><span class="label">健康度</span><strong>{{ result.health_score }}</strong></div>
      <div class="metric"><span class="label">故障概率</span><strong>{{ percent(result.fault_likelihood) }}</strong></div>
      <div class="metric"><span class="label">故障标签</span><strong>{{ result.fault_label || '-' }}</strong></div>
      <div class="metric"><span class="label">转频</span><strong>{{ result.rot_freq_hz ?? '-' }} Hz</strong></div>
    </div>

    <!-- 单方法结果摘要 -->
    <div v-if="result && runMode === 'single'" class="summary-band">
      <div class="metric">
        <span class="label">方法</span>
        <el-tag :type="methodCategoryTag" size="large">{{ selectedMethodInfo?.label || selectedMethod }}</el-tag>
      </div>
      <div class="metric"><span class="label">转频</span><strong>{{ result.rot_freq_hz ?? '-' }} Hz</strong></div>
      <div class="metric" v-if="result.health_score"><span class="label">健康度</span><strong>{{ result.health_score }}</strong></div>
      <div class="metric" v-if="result.status"><span class="label">状态</span><el-tag :type="statusType(result.status)">{{ statusText(result.status) }}</el-tag></div>
    </div>

    <el-empty v-if="!result && !loading" :description="runMode === 'single' ? '请选择分析方法后运行' : '请点击运行开始诊断'" />

    <!-- ========== 单方法结果详情 ========== -->
    <div v-if="result && runMode === 'single'" class="result-grid">
      <!-- 轴承方法 -->
      <template v-if="selectedMethodInfo?.category === 'bearing'">
        <section class="panel">
          <div class="panel-title">包络域特征</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="包络峰值SNR">{{ fmt(result.features?.envelope_peak_snr) }}</el-descriptions-item>
            <el-descriptions-item label="包络峭度">{{ fmt(result.features?.envelope_kurtosis) }}</el-descriptions-item>
          </el-descriptions>
        </section>
        <section class="panel">
          <div class="panel-title">轴承故障指示器</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item v-for="(val, name) in result.fault_indicators" :key="name" :label="name">
              <template v-if="val && typeof val === 'object'">
                <el-tag :type="val.significant ? 'danger' : val.warning ? 'warning' : 'success'" size="small">{{ val.significant ? '命中' : val.warning ? '预警' : '正常' }}</el-tag>
                <span v-if="val.snr" style="margin-left:4px">SNR={{ fmt(val.snr) }}</span>
                <span v-if="val.value" style="margin-left:4px">值={{ fmt(val.value) }}</span>
              </template>
              <template v-else>{{ fmt(val) }}</template>
            </el-descriptions-item>
          </el-descriptions>
        </section>
      </template>

      <!-- 齿轮方法 -->
      <template v-if="selectedMethodInfo?.category === 'gear'">
        <section class="panel">
          <div class="panel-title">齿轮指标</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="SER">{{ fmt(result.ser) }}</el-descriptions-item>
            <el-descriptions-item label="CAR">{{ fmt(result.car) }}</el-descriptions-item>
            <el-descriptions-item v-if="result.fm0" label="FM0">{{ fmt(result.fm0) }}</el-descriptions-item>
            <el-descriptions-item v-if="result.fm4" label="FM4">{{ fmt(result.fm4) }}</el-descriptions-item>
            <el-descriptions-item v-if="result.m6a" label="M6A">{{ fmt(result.m6a) }}</el-descriptions-item>
            <el-descriptions-item v-if="result.m8a" label="M8A">{{ fmt(result.m8a) }}</el-descriptions-item>
            <el-descriptions-item v-if="result.mesh_freq_hz" label="啮合频率">{{ fmt(result.mesh_freq_hz) }} Hz</el-descriptions-item>
            <el-descriptions-item v-if="result.mesh_order" label="啮合阶次">{{ fmt(result.mesh_order) }}</el-descriptions-item>
          </el-descriptions>
        </section>
        <section class="panel">
          <div class="panel-title">齿轮故障指示器</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item v-for="(val, name) in result.fault_indicators" :key="name" :label="name">
              <template v-if="val && typeof val === 'object'">
                <el-tag :type="val.critical ? 'danger' : val.warning ? 'warning' : 'success'" size="small">{{ val.critical ? '严重' : val.warning ? '预警' : '正常' }}</el-tag>
                <span v-if="val.value" style="margin-left:4px">值={{ fmt(val.value) }}</span>
              </template>
              <template v-else>{{ fmt(val) }}</template>
            </el-descriptions-item>
          </el-descriptions>
        </section>
      </template>

      <!-- 行星箱方法 -->
      <template v-if="selectedMethodInfo?.category === 'planetary'">
        <section class="panel">
          <div class="panel-title">{{ selectedMethodInfo.label }} 结果</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item v-for="(val, name) in filterPlanetaryResult" :key="name" :label="name">{{ fmt(val) }}</el-descriptions-item>
          </el-descriptions>
        </section>
        <section v-if="result.fault_indicators" class="panel">
          <div class="panel-title">故障指示器</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item v-for="(val, name) in result.fault_indicators" :key="name" :label="name">
              <template v-if="val && typeof val === 'object'">
                <el-tag :type="val.critical ? 'danger' : val.significant ? 'warning' : 'success'" size="small">{{ val.critical ? '严重' : val.significant ? '显著' : '正常' }}</el-tag>
              </template>
              <template v-else>{{ fmt(val) }}</template>
            </el-descriptions-item>
          </el-descriptions>
        </section>
      </template>
    </div>

    <!-- ========== 全方法/集成诊断结果详情 ========== -->
    <div v-if="result && runMode !== 'single'" class="grid">
      <!-- D-S 证据融合面板 -->
      <section v-if="result.ensemble?.ds_fusion" class="panel">
        <div class="panel-title">
          <span>D-S 证据融合</span>
          <el-tag v-if="result.ensemble?.ds_fusion?.conflict_coefficient > 0.8" type="danger" effect="plain" size="small">高冲突</el-tag>
          <el-tag v-else type="success" effect="plain" size="small">低冲突</el-tag>
        </div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="主导故障">{{ result.ensemble?.ds_fusion?.dominant_fault || '-' }}</el-descriptions-item>
          <el-descriptions-item label="主导概率">{{ percent(result.ensemble?.ds_fusion?.dominant_probability) }}</el-descriptions-item>
          <el-descriptions-item label="不确定性(Θ)">{{ percent(result.ensemble?.ds_fusion?.uncertainty) }}</el-descriptions-item>
          <el-descriptions-item label="冲突系数">{{ fmt(result.ensemble?.ds_fusion?.conflict_coefficient) }}</el-descriptions-item>
        </el-descriptions>
      </section>

      <section class="panel">
        <div class="panel-title">
          <span>集成证据</span>
          <el-tag effect="plain">{{ result.ensemble?.profile }}</el-tag>
        </div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="轴承置信度">{{ percent(result.ensemble?.bearing_confidence) }}</el-descriptions-item>
          <el-descriptions-item label="齿轮置信度">{{ percent(result.ensemble?.gear_confidence) }}</el-descriptions-item>
          <el-descriptions-item label="时域置信度">{{ percent(result.ensemble?.time_confidence) }}</el-descriptions-item>
          <el-descriptions-item label="轴承投票率">{{ percent(result.ensemble?.bearing_vote_fraction) }}</el-descriptions-item>
          <el-descriptions-item label="最佳轴承算法">{{ result.ensemble?.best_bearing || '-' }}</el-descriptions-item>
          <el-descriptions-item label="最佳齿轮算法">{{ result.ensemble?.best_gear || '-' }}</el-descriptions-item>
        </el-descriptions>
      </section>

      <section class="panel">
        <div class="panel-title">时域指标</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="RMS">{{ fmt(result.time_features?.rms) }}</el-descriptions-item>
          <el-descriptions-item label="峭度">{{ fmt(result.time_features?.kurtosis) }}</el-descriptions-item>
          <el-descriptions-item label="峰值因子">{{ fmt(result.time_features?.crest_factor) }}</el-descriptions-item>
          <el-descriptions-item label="RMS MAD-Z">{{ fmt(result.time_features?.rms_mad_z) }}</el-descriptions-item>
          <el-descriptions-item label="CUSUM">{{ fmt(result.time_features?.cusum_score) }}</el-descriptions-item>
          <el-descriptions-item label="EWMA">{{ fmt(result.time_features?.ewma_drift) }}</el-descriptions-item>
        </el-descriptions>
      </section>

      <!-- D-S 融合故障概率分布表 -->
      <section v-if="result.ensemble?.ds_fusion?.fused_bpa" class="panel wide">
        <div class="panel-title">D-S 融合故障概率分布</div>
        <el-table :data="dsFaultProbRows" border size="small" max-height="300">
          <el-table-column prop="fault" label="故障类型" min-width="180" />
          <el-table-column prop="bpa" label="概率(BPA)" width="120">
            <template #default="{ row }">{{ percent(row.bpa) }}</template>
          </el-table-column>
          <el-table-column prop="belief" label="信念(Bel)" width="120">
            <template #default="{ row }">{{ percent(row.belief) }}</template>
          </el-table-column>
          <el-table-column prop="plausibility" label="似然(Pl)" width="120">
            <template #default="{ row }">{{ percent(row.plausibility) }}</template>
          </el-table-column>
        </el-table>
      </section>

      <section class="panel wide">
        <div class="panel-title">轴承算法投票</div>
        <el-table :data="bearingVoteRows" border size="small" max-height="320">
          <el-table-column prop="method" label="算法" min-width="180" />
          <el-table-column prop="confidence" label="置信度" width="110">
            <template #default="{ row }">{{ percent(row.confidence) }}</template>
          </el-table-column>
          <el-table-column prop="param_hits" label="参数命中" width="100" />
          <el-table-column prop="stat_hits" label="统计命中" width="100" />
          <el-table-column prop="strongest_snr" label="最强SNR" width="100" />
          <el-table-column prop="hits" label="证据" min-width="220" />
        </el-table>
      </section>

      <section class="panel wide">
        <div class="panel-title">齿轮算法投票</div>
        <el-table :data="gearVoteRows" border size="small" max-height="260">
          <el-table-column prop="method" label="算法" min-width="180" />
          <el-table-column prop="confidence" label="置信度" width="110">
            <template #default="{ row }">{{ percent(row.confidence) }}</template>
          </el-table-column>
          <el-table-column prop="critical_hits" label="严重命中" width="100" />
          <el-table-column prop="warning_hits" label="预警命中" width="100" />
          <el-table-column prop="hits" label="证据" min-width="220" />
        </el-table>
      </section>

      <section class="panel wide">
        <div class="panel-title">最佳算法指标</div>
        <el-table :data="bestIndicatorRows" border size="small" max-height="320">
          <el-table-column prop="source" label="来源" width="90" />
          <el-table-column prop="name" label="指标" min-width="160" />
          <el-table-column prop="value" label="数值" min-width="140" />
          <el-table-column prop="state" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.type" size="small">{{ row.state }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Cpu, DataLine } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { getAllDeviceData, getMethodInfo, getChannelMethodAnalysis, getChannelResearchAnalysis } from '../api'

const route = useRoute()
const router = useRouter()
const devices = ref([])
const selectedDeviceId = ref('')
const selectedBatchIndex = ref(null)
const selectedChannel = ref(1)
const runMode = ref('single')
const selectedMethod = ref('envelope')
const denoise = ref('none')
const profile = ref('balanced')
const loading = ref(false)
const result = ref(null)
const methodInfoData = ref({})

const runModeOptions = [
  { label: '单方法', value: 'single' },
  { label: '全部方法', value: 'all' },
  { label: '集成诊断', value: 'ensemble' },
]

const currentDevice = computed(() => devices.value.find(d => d.device_id === selectedDeviceId.value))
const currentBatches = computed(() => currentDevice.value?.batches || [])
const currentChannels = computed(() => {
  const count = currentDevice.value?.channel_count || 3
  const names = currentDevice.value?.channel_names || {}
  return Array.from({ length: count }, (_, i) => ({
    value: i + 1,
    label: names[String(i + 1)] || `通道 ${i + 1}`,
  }))
})
const canRun = computed(() => selectedDeviceId.value && selectedBatchIndex.value != null && selectedChannel.value)

// 方法分组
const bearingMethodGroup = computed(() =>
  Object.entries(methodInfoData.value).filter(([_, m]) => m.category === 'bearing').map(([k, m]) => ({ key: k, label: m.label }))
)
const gearMethodGroup = computed(() =>
  Object.entries(methodInfoData.value).filter(([_, m]) => m.category === 'gear').map(([k, m]) => ({ key: k, label: m.label }))
)
const planetaryMethodGroup = computed(() =>
  Object.entries(methodInfoData.value).filter(([_, m]) => m.category === 'planetary').map(([k, m]) => ({ key: k, label: m.label }))
)

const selectedMethodInfo = computed(() => methodInfoData.value[selectedMethod.value] || null)
const methodCategoryTag = computed(() => {
  const cat = selectedMethodInfo.value?.category
  if (cat === 'bearing') return 'primary'
  if (cat === 'gear') return 'warning'
  if (cat === 'planetary') return 'danger'
  return 'info'
})

// 行星箱判断
const hasPlanetary = computed(() => {
  const d = currentDevice.value
  if (!d) return false
  const gt = d.gear_teeth
  if (!gt) return false
  // 通道级格式
  for (const [, v] of Object.entries(gt)) {
    if (typeof v === 'object' && (v?.planet_count >= 3 || (v?.sun > 0 && v?.ring > 0))) return true
  }
  if (gt.planet_count >= 3 || (gt.sun > 0 && gt.ring > 0)) return true
  return false
})

// 行星箱方法结果过滤（排除大数组/不可展示字段）
const filterPlanetaryResult = computed(() => {
  if (!result.value || selectedMethodInfo.value?.category !== 'planetary') return {}
  const filtered = {}
  for (const [k, v] of Object.entries(result.value)) {
    if (typeof v === 'number' || typeof v === 'string' || typeof v === 'boolean') {
      filtered[k] = v
    }
  }
  return filtered
})

// 投票行数据
const bearingVoteRows = computed(() => voteRows(result.value?.ensemble?.bearing_votes))
const gearVoteRows = computed(() => voteRows(result.value?.ensemble?.gear_votes))

const bestIndicatorRows = computed(() => {
  const rows = []
  appendIndicators(rows, '轴承', result.value?.bearing?.fault_indicators)
  appendIndicators(rows, '齿轮', result.value?.gear?.fault_indicators)
  return rows
})

// D-S 融合故障概率行
const dsFaultProbRows = computed(() => {
  const bpa = result.value?.ensemble?.ds_fusion?.fused_bpa
  const belief = result.value?.ensemble?.ds_fusion?.fused_belief
  const plaus = result.value?.ensemble?.ds_fusion?.fused_plausibility
  if (!bpa) return []
  return Object.entries(bpa)
    .filter(([k]) => k !== 'Θ')
    .map(([fault, prob]) => ({
      fault,
      bpa: prob,
      belief: belief?.[fault] ?? 0,
      plausibility: plaus?.[fault] ?? 0,
    }))
    .sort((a, b) => b.bpa - a.bpa)
})

watch(selectedDeviceId, () => {
  selectedBatchIndex.value = currentBatches.value[0]?.batch_index ?? null
  selectedChannel.value = currentChannels.value[0]?.value ?? 1
  result.value = null
})

watch(runMode, () => { result.value = null })

const loadDevices = async () => {
  const res = await getAllDeviceData()
  devices.value = res.data || []
  // 从路由 query 参数预选设备/批次/通道（联动跳转）
  const qDevice = route.query.device_id
  const qBatch = route.query.batch_index
  const qChannel = route.query.channel
  if (qDevice && devices.value.length > 0) {
    selectedDeviceId.value = qDevice
    const dev = devices.value.find(d => d.device_id === qDevice)
    if (dev) {
      const batch = dev.batches?.find(b => String(b.batch_index) === String(qBatch))
      if (batch) {
        selectedBatchIndex.value = batch.batch_index
      }
      if (qChannel) {
        const ch = parseInt(qChannel)
        const count = dev.channel_count || 3
        if (ch >= 1 && ch <= count) {
          selectedChannel.value = ch
        }
      }
    }
  } else if (devices.value.length > 0 && !selectedDeviceId.value) {
    selectedDeviceId.value = devices.value[0].device_id
  }
}

const loadMethodInfo = async () => {
  try {
    const res = await getMethodInfo()
    methodInfoData.value = res.data || {}
  } catch (e) {
    methodInfoData.value = {}
  }
}

const runAnalysis = async () => {
  if (!canRun.value) return
  loading.value = true
  result.value = null
  try {
    if (runMode.value === 'single') {
      const res = await getChannelMethodAnalysis(
        selectedDeviceId.value,
        selectedBatchIndex.value,
        selectedChannel.value,
        selectedMethod.value,
        { denoise: denoise.value },
      )
      result.value = res.data
    } else if (runMode.value === 'all') {
      const res = await getChannelMethodAnalysis(
        selectedDeviceId.value,
        selectedBatchIndex.value,
        selectedChannel.value,
        'all',
        { denoise: denoise.value },
      )
      result.value = res.data
    } else if (runMode.value === 'ensemble') {
      const res = await getChannelResearchAnalysis(
        selectedDeviceId.value,
        selectedBatchIndex.value,
        selectedChannel.value,
        { profile: profile.value, denoise: denoise.value },
      )
      result.value = res.data
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '诊断失败')
  } finally {
    loading.value = false
  }
}

const voteRows = (votes = {}) => Object.entries(votes).map(([method, value]) => ({
  method,
  confidence: value.confidence ?? 0,
  param_hits: value.param_hits ?? '-',
  stat_hits: value.stat_hits ?? '-',
  critical_hits: value.critical_hits ?? '-',
  warning_hits: value.warning_hits ?? '-',
  strongest_snr: value.strongest_snr ?? '-',
  hits: Array.isArray(value.hits) ? value.hits.join(', ') : '',
}))

const appendIndicators = (rows, source, indicators = {}) => {
  Object.entries(indicators || {}).forEach(([name, value]) => {
    if (!value || typeof value !== 'object') return
    const isCritical = value.critical || value.significant
    const isWarning = value.warning
    rows.push({
      source,
      name,
      value: value.value ?? value.snr ?? value.detected_hz ?? '-',
      state: isCritical ? '命中' : isWarning ? '预警' : '正常',
      type: isCritical ? 'danger' : isWarning ? 'warning' : 'success',
    })
  })
}

const fmt = value => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(4) : '-'
}

const percent = value => {
  const num = Number(value)
  return Number.isFinite(num) ? `${(num * 100).toFixed(1)}%` : '-'
}

const statusType = status => {
  if (status === 'fault' || status === 'critical') return 'danger'
  if (status === 'warning') return 'warning'
  return 'success'
}

const statusText = status => {
  if (status === 'fault' || status === 'critical') return '故障'
  if (status === 'warning') return '预警'
  return '正常'
}

onMounted(() => {
  loadDevices()
  loadMethodInfo()
})

// 跳转到数据查看页面，携带当前设备/批次参数
const gotoDataView = () => {
  if (!selectedDeviceId.value || selectedBatchIndex.value == null) return
  router.push({
    path: '/data',
    query: {
      device_id: selectedDeviceId.value,
      batch_index: selectedBatchIndex.value,
    }
  })
}
</script>

<style scoped>
.research-diagnosis {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.selectors {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.select { width: 190px; }
.select.small { width: 130px; }
.method-select { width: 220px; }

.method-desc-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #f0f9ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
}

.method-desc-text {
  color: #475569;
  font-size: 14px;
  line-height: 1.5;
}

.summary-band {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  padding: 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.metric {
  min-height: 68px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}

.label { color: #6b7280; font-size: 13px; }
.metric strong { font-size: 20px; color: #111827; }

.result-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  min-width: 0;
}

.panel.wide { grid-column: 1 / -1; }

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  margin-bottom: 12px;
}

@media (max-width: 1100px) {
  .toolbar { align-items: stretch; flex-direction: column; }
  .select, .select.small, .method-select { width: 100%; }
  .summary-band, .grid, .result-grid { grid-template-columns: 1fr; }
}
</style>