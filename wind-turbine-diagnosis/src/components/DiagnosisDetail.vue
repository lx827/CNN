<template>
  <div v-if="data" class="diagnosis-detail">
    <!-- 综合结论 -->
    <div class="detail-group">
      <div class="group-title">📋 综合结论</div>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="健康度">
          <span :class="scoreClass(data.health_score)">{{ data.health_score }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusTagType(data.status)" size="small" effect="dark">{{ statusText(data.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="故障概率">
          {{ data.fault_likelihood != null ? (data.fault_likelihood * 100).toFixed(1) + '%' : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="故障类型">
          {{ faultLabelText(data.fault_label) }}
        </el-descriptions-item>
        <el-descriptions-item label="转频" :span="2">
          {{ displayRotFreq != null ? displayRotFreq.toFixed(2) + ' Hz / ' + (displayRotFreq * 60).toFixed(0) + ' RPM' : '-' }}
        </el-descriptions-item>
      </el-descriptions>
      <el-text v-if="data.recommendation" type="info" size="small" style="margin-top: 6px; display: block;">
        💡 {{ data.recommendation }}
      </el-text>
    </div>

    <!-- 时域特征 -->
    <div class="detail-group" v-if="data.time_features">
      <div class="group-title">⏱ 时域特征</div>
      <el-descriptions :column="3" size="small" border>
        <el-descriptions-item v-for="item in timeFeatureItems" :key="item.key" :label="item.label">
          <span :class="{ 'text-danger': item.warn }">{{ fmtVal(item.value, item.precision) }}</span>
          <el-text v-if="item.normal" type="info" size="small" class="val-hint">{{ item.normal }}</el-text>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 轴承故障指示器 -->
    <div class="detail-group" v-if="bearingIndicators.length">
      <div class="group-title">🔩 轴承故障指示器</div>
      <el-descriptions :column="3" size="small" border>
        <el-descriptions-item v-for="item in bearingIndicators" :key="item.key" :label="item.label">
          <span :class="item.significant ? 'text-warning' : 'text-muted'">{{ fmtVal(item.value) }}</span>
          <el-tag v-if="item.significant" type="warning" size="small" style="margin-left: 4px;">显著</el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 齿轮故障指示器 -->
    <div class="detail-group" v-if="gearIndicators.length">
      <div class="group-title">⚙ 齿轮故障指示器</div>
      <el-descriptions :column="3" size="small" border>
        <el-descriptions-item v-for="item in gearIndicators" :key="item.key" :label="item.label">
          <span :class="item.level">{{ fmtVal(item.value) }}</span>
          <el-tag v-if="item.critical" type="danger" size="small" style="margin-left: 4px;">严重</el-tag>
          <el-tag v-else-if="item.warning" type="warning" size="small" style="margin-left: 4px;">预警</el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 轴承特征频率 (仅当有参数级数据时显示) -->
    <div class="detail-group" v-if="bearingFreqItems.length">
      <div class="group-title">🎵 轴承特征频率</div>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item v-for="item in bearingFreqItems" :key="item.key" :label="item.label">
          {{ fmtVal(item.value) }} Hz
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 齿轮特征频率 (仅当有参数级数据时显示) -->
    <div class="detail-group" v-if="gearFreqItems.length">
      <div class="group-title">🎵 齿轮特征频率</div>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item v-for="item in gearFreqItems" :key="item.key" :label="item.label">
          {{ fmtVal(item.value) }} Hz
        </el-descriptions-item>
      </el-descriptions>
    </div>
  </div>
  <div v-else class="placeholder">
    <el-empty description="无诊断数据" :image-size="80" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  orderAnalysis: { type: Object, default: null },
  rotFreq: { type: Number, default: null },
  rotRpm: { type: Number, default: null },
})

// engine_result 是 order_analysis 的核心数据
const data = computed(() => {
  if (!props.orderAnalysis) return null
  // order_analysis 可能是嵌套结构 { engine_result: {...}, channels: {...} }
  if (props.orderAnalysis.engine_result) {
    return props.orderAnalysis.engine_result
  }
  // 也可能直接是 engine_result 本身
  return props.orderAnalysis
})

const displayRotFreq = computed(() => {
  if (props.rotFreq != null) return props.rotFreq
  return data.value?.rot_freq_hz ?? null
})

// ---- 综合结论 ----
function scoreClass(hs) {
  if (hs >= 85) return 'score-good'
  if (hs >= 60) return 'score-warning'
  return 'score-danger'
}
function statusTagType(s) {
  return s === 'normal' ? 'success' : s === 'warning' ? 'warning' : 'danger'
}
function statusText(s) {
  return s === 'normal' ? '正常' : s === 'warning' ? '预警' : '故障'
}
function faultLabelText(label) {
  if (!label || label === 'unknown') return '未检出异常'
  if (label === 'bearing_abnormal') return '轴承异常'
  if (label === 'gear_abnormal') return '齿轮异常'
  if (label.startsWith('bearing_')) return '轴承 ' + label.replace('bearing_', '')
  return label
}

// ---- 时域特征 ----
const timeFeatureDefs = {
  peak: { label: '峰值', precision: 4 },
  rms: { label: '均方根', precision: 4 },
  mean_abs: { label: '平均绝对值', precision: 4 },
  kurtosis: { label: '峭度', precision: 2, normal: '≈3', warn: v => v > 5 },
  skewness: { label: '偏度', precision: 2, normal: '≈0' },
  crest_factor: { label: '峰值因子', precision: 2, normal: '3~5', warn: v => v > 10 },
  shape_factor: { label: '波形因子', precision: 2, normal: '≈1.11' },
  impulse_factor: { label: '脉冲因子', precision: 2 },
  margin: { label: '裕度', precision: 2 },
  rms_mad_z: { label: 'RMS基线漂移', precision: 2 },
  kurtosis_mad_z: { label: '峭度基线漂移', precision: 2 },
  ewma_drift: { label: 'EWMA漂移', precision: 4 },
  cusum_score: { label: 'CUSUM累积', precision: 2 },
}

const timeFeatureItems = computed(() => {
  const tf = data.value?.time_features || {}
  const items = []
  for (const [key, def] of Object.entries(timeFeatureDefs)) {
    if (tf[key] !== undefined && tf[key] !== null) {
      const v = tf[key]
      items.push({
        key,
        label: def.label,
        value: v,
        precision: def.precision,
        normal: def.normal,
        warn: def.warn ? def.warn(v) : false,
      })
    }
  }
  return items
})

// ---- 轴承故障指示器 ----
const indicatorLabelMap = {
  envelope_peak_snr: '包络峰值信噪比',
  envelope_kurtosis: '包络峭度',
  moderate_kurtosis: '中等峭度',
  envelope_crest_factor: '包络峰值因子',
  peak_concentration: '峰值集中度',
  high_freq_ratio: '高频比',
  low_freq_ratio: '低频比',
  envelope_peak_snr_stat: '包络峰值SNR(统计)',
  envelope_kurtosis_stat: '包络峭度(统计)',
  moderate_kurtosis_stat: '中等峭度(统计)',
  rotation_harmonic_dominant: '旋转谐波占优',
  BPFO: '外圈(BPFO)',
  BPFI: '内圈(BPFI)',
  BSF: '滚动体(BSF)',
  FTF: '保持架(FTF)',
}

const bearingIndicators = computed(() => {
  const bi = data.value?.bearing?.fault_indicators || {}
  const items = []
  for (const [k, v] of Object.entries(bi)) {
    if (typeof v !== 'object' || v === null) continue
    items.push({
      key: k,
      label: indicatorLabelMap[k] || k,
      value: v.value ?? v.snr ?? v.ratio ?? null,
      significant: v.significant ?? false,
    })
  }
  return items
})

const gearIndicators = computed(() => {
  const gi = data.value?.gear?.fault_indicators || {}
  const items = []
  for (const [k, v] of Object.entries(gi)) {
    if (typeof v !== 'object' || v === null) continue
    items.push({
      key: k,
      label: indicatorLabelMap[k] || k,
      value: v.value ?? v.ratio ?? v.score ?? null,
      warning: v.warning ?? false,
      critical: v.critical ?? false,
      level: v.critical ? 'text-danger' : v.warning ? 'text-warning' : 'text-muted',
    })
  }
  return items
})

// ---- 特征频率 ----
const bearingFreqItems = computed(() => {
  const bi = data.value?.bearing?.fault_indicators || {}
  const items = []
  for (const key of ['BPFO', 'BPFI', 'BSF', 'FTF']) {
    if (bi[key]?.frequency_hz) {
      items.push({ key, label: indicatorLabelMap[key], value: bi[key].frequency_hz })
    }
  }
  return items
})

const gearFreqItems = computed(() => {
  const gi = data.value?.gear || {}
  const items = []
  if (gi.mesh_freq_hz) items.push({ key: 'mesh_freq_hz', label: '啮合频率', value: gi.mesh_freq_hz })
  if (gi.output_mesh_freq_hz) items.push({ key: 'output_mesh_freq_hz', label: '输出轴啮合频率', value: gi.output_mesh_freq_hz })
  return items
})

// ---- 工具函数 ----
function fmtVal(v, precision = 4) {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'number') {
    if (Math.abs(v) < 0.001) return v.toExponential(2)
    return v.toFixed(precision)
  }
  return String(v)
}
</script>

<style scoped>
.diagnosis-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-group {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 12px 16px;
}

.group-title {
  font-weight: 600;
  font-size: 14px;
  color: #1d2129;
  margin-bottom: 8px;
}

.val-hint {
  margin-left: 6px;
  font-size: 12px;
}

.score-good { color: #52c41a; font-weight: 600; font-size: 18px; }
.score-warning { color: #faad14; font-weight: 600; font-size: 18px; }
.score-danger { color: #f5222d; font-weight: 600; font-size: 18px; }

.text-danger { color: #f5222d; font-weight: bold; }
.text-warning { color: #faad14; font-weight: 600; }
.text-muted { color: #666; }
</style>