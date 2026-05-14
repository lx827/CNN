<template>
  <div class="research-diagnosis">
    <div class="toolbar">
      <div class="selectors">
        <el-select v-model="selectedDeviceId" placeholder="设备" filterable class="select">
          <el-option
            v-for="device in devices"
            :key="device.device_id"
            :label="device.device_name || device.device_id"
            :value="device.device_id"
          />
        </el-select>

        <el-select v-model="selectedBatchIndex" placeholder="批次" filterable class="select small">
          <el-option
            v-for="batch in currentBatches"
            :key="batch.batch_index"
            :label="`#${batch.batch_index}`"
            :value="batch.batch_index"
          />
        </el-select>

        <el-select v-model="selectedChannel" placeholder="通道" class="select small">
          <el-option
            v-for="channel in currentChannels"
            :key="channel.value"
            :label="channel.label"
            :value="channel.value"
          />
        </el-select>

        <el-segmented v-model="profile" :options="profileOptions" />

        <el-select v-model="denoise" class="select small">
          <el-option label="不去噪" value="none" />
          <el-option label="小波" value="wavelet" />
          <el-option label="VMD" value="vmd" />
        </el-select>

        <el-input-number v-model="maxSeconds" :min="1" :max="10" :step="1" size="default" />
      </div>

      <el-button type="primary" :loading="loading" :disabled="!canRun" @click="runAnalysis">
        <el-icon><Cpu /></el-icon>
        <span>运行</span>
      </el-button>
    </div>

    <div v-if="result" class="summary-band">
      <div class="metric">
        <span class="label">状态</span>
        <el-tag :type="statusType(result.status)" size="large">{{ statusText(result.status) }}</el-tag>
      </div>
      <div class="metric">
        <span class="label">健康度</span>
        <strong>{{ result.health_score }}</strong>
      </div>
      <div class="metric">
        <span class="label">故障概率</span>
        <strong>{{ percent(result.fault_likelihood) }}</strong>
      </div>
      <div class="metric">
        <span class="label">故障标签</span>
        <strong>{{ result.fault_label || '-' }}</strong>
      </div>
      <div class="metric">
        <span class="label">转频</span>
        <strong>{{ result.rot_freq_hz ?? '-' }} Hz</strong>
      </div>
    </div>

    <el-empty v-if="!result && !loading" description="暂无高级诊断结果" />

    <div v-if="result" class="grid">
      <section class="panel">
        <div class="panel-title">
          <span>集成证据</span>
          <el-tag effect="plain">{{ result.profile }}</el-tag>
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
import { getAllDeviceData, getChannelResearchAnalysis } from '../api'

const devices = ref([])
const selectedDeviceId = ref('')
const selectedBatchIndex = ref(null)
const selectedChannel = ref(1)
const profile = ref('balanced')
const denoise = ref('none')
const maxSeconds = ref(5)
const loading = ref(false)
const result = ref(null)

const profileOptions = [
  { label: '运行级', value: 'runtime' },
  { label: '均衡', value: 'balanced' },
  { label: '全量', value: 'exhaustive' },
]

const currentDevice = computed(() => devices.value.find(d => d.device_id === selectedDeviceId.value))
const currentBatches = computed(() => currentDevice.value?.batches || [])
const currentChannels = computed(() => {
  const count = currentDevice.value?.channel_count || 3
  const names = currentDevice.value?.channel_names || {}
  return Array.from({ length: count }, (_, i) => {
    const value = i + 1
    return { value, label: names[String(value)] || `通道 ${value}` }
  })
})
const canRun = computed(() => selectedDeviceId.value && selectedBatchIndex.value != null && selectedChannel.value)

const bearingVoteRows = computed(() => voteRows(result.value?.ensemble?.bearing_votes))
const gearVoteRows = computed(() => voteRows(result.value?.ensemble?.gear_votes))
const bestIndicatorRows = computed(() => {
  const rows = []
  appendIndicators(rows, '轴承', result.value?.bearing?.fault_indicators)
  appendIndicators(rows, '齿轮', result.value?.gear?.fault_indicators)
  return rows
})

watch(selectedDeviceId, () => {
  selectedBatchIndex.value = currentBatches.value[0]?.batch_index ?? null
  selectedChannel.value = currentChannels.value[0]?.value ?? 1
  result.value = null
})

const loadDevices = async () => {
  const res = await getAllDeviceData()
  devices.value = res.data || []
  if (devices.value.length > 0 && !selectedDeviceId.value) {
    selectedDeviceId.value = devices.value[0].device_id
  }
}

const runAnalysis = async () => {
  if (!canRun.value) return
  loading.value = true
  try {
    const res = await getChannelResearchAnalysis(
      selectedDeviceId.value,
      selectedBatchIndex.value,
      selectedChannel.value,
      {
        profile: profile.value,
        denoise: denoise.value,
        max_seconds: maxSeconds.value,
      }
    )
    result.value = res.data
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '高级诊断失败')
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

onMounted(loadDevices)
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

.select {
  width: 190px;
}

.select.small {
  width: 130px;
}

.summary-band {
  display: grid;
  grid-template-columns: repeat(5, minmax(150px, 1fr));
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

.label {
  color: #6b7280;
  font-size: 13px;
}

.metric strong {
  font-size: 20px;
  color: #111827;
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

.panel.wide {
  grid-column: 1 / -1;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  margin-bottom: 12px;
}

@media (max-width: 1100px) {
  .toolbar,
  .summary-band,
  .grid {
    grid-template-columns: 1fr;
  }

  .toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .select,
  .select.small {
    width: 100%;
  }
}
</style>
