<template>
  <el-row v-if="orderAnalysis" :gutter="16">
    <el-col :span="24">
      <el-card size="small" style="margin-bottom: 16px">
        <template #header>
          <span style="font-weight: 600;">🔍 频域/阶次诊断明细</span>
          <el-text v-if="displayRotFreq != null" type="info" size="small" style="margin-left: 12px;">
            估计转频: {{ displayRotFreq.toFixed(2) }} Hz / {{ (displayRotFreq * 60).toFixed(0) }} RPM
          </el-text>
        </template>
        <el-descriptions :column="2" size="small" border>
          <template v-for="item in flatItems" :key="item.key">
            <el-descriptions-item :label="item.label" v-if="item.value !== null && item.value !== undefined">
              <span :class="{ 'text-danger': isAnomalyKey(item.key, item.value) }">{{ formatValue(item.value) }}</span>
            </el-descriptions-item>
          </template>
        </el-descriptions>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  orderAnalysis: { type: Object, default: null },
  rotFreq: { type: Number, default: null },
  rotRpm: { type: Number, default: null },
})

const displayRotFreq = computed(() => {
  return props.rotFreq ?? (props.orderAnalysis?.rot_freq_hz || null)
})

const keyLabelMap = {
  'rot_freq_hz': '转频',
  'rot_rpm': '转速',
  'spectrum_features': '频谱特征',
  'envelope_features': '包络特征',
  'order_features': '阶次特征',
  'mesh_freq_hz': '啮合频率',
  'mesh_freq_ratio': '啮合频率能量比',
  'sideband_total_ratio': '边频带总能量比',
  'sideband_count': '边频带数量',
  'output_mesh_freq_hz': '输出轴啮合频率',
  'output_mesh_ratio': '输出轴啮合能量比',
  'BPFO_hz': '外圈故障频率',
  'BPFI_hz': '内圈故障频率',
  'BSF_hz': '滚动体故障频率',
  'FTF_hz': '保持架故障频率',
  'BPFO_ratio': '外圈能量比',
  'BPFI_ratio': '内圈能量比',
  'BSF_ratio': '滚动体能量比',
  'FTF_ratio': '保持架能量比',
  'BPFO_harmonic_ratio': '外圈谐波能量比',
  'BPFI_harmonic_ratio': '内圈谐波能量比',
  'BSF_harmonic_ratio': '滚动体谐波能量比',
  'FTF_harmonic_ratio': '保持架谐波能量比',
  'BPFO_env_ratio': '外圈包络能量比',
  'BPFI_env_ratio': '内圈包络能量比',
  'BSF_env_ratio': '滚动体包络能量比',
  'FTF_env_ratio': '保持架包络能量比',
  'BPFO_env_harmonic_ratio': '外圈包络谐波能量比',
  'BPFI_env_harmonic_ratio': '内圈包络谐波能量比',
  'BSF_env_harmonic_ratio': '滚动体包络谐波能量比',
  'FTF_env_harmonic_ratio': '保持架包络谐波能量比',
  'total_env_energy': '包络总能量',
  'mesh_order': '啮合阶次',
  'mesh_order_ratio': '啮合阶次能量比',
  'sideband_order_total_ratio': '边频阶次总能量比',
  'sideband_order_count': '边频阶次数量',
  'output_mesh_order': '输出轴啮合阶次',
  'output_mesh_order_ratio': '输出轴啮合阶次能量比',
  'BPFO_order': '外圈故障阶次',
  'BPFI_order': '内圈故障阶次',
  'BSF_order': '滚动体故障阶次',
  'FTF_order': '保持架故障阶次',
  'BPFO_order_ratio': '外圈阶次能量比',
  'BPFI_order_ratio': '内圈阶次能量比',
  'BSF_order_ratio': '滚动体阶次能量比',
  'FTF_order_ratio': '保持架阶次能量比',
  'BPFO_order_harmonic_ratio': '外圈阶次谐波能量比',
  'BPFI_order_harmonic_ratio': '内圈阶次谐波能量比',
  'BSF_order_harmonic_ratio': '滚动体阶次谐波能量比',
  'FTF_order_harmonic_ratio': '保持架阶次谐波能量比',
  'engine_result': '引擎结果',
  'channels': '各通道',
  'bearing': '轴承',
  'gear': '齿轮',
  'method': '方法',
  'strategy': '策略',
  'health_score': '健康度',
  'status': '状态',
  'time_features': '时域特征',
  'recommendation': '建议',
  'fault_indicators': '故障指示器',
  'envelope_freq': '包络频率',
  'envelope_amp': '包络幅值',
  'band_center': '中心频率',
  'band_width': '带宽',
  'optimal_fc': '最优中心频率',
  'optimal_bw': '最优带宽',
  'max_kurtosis': '最大峭度',
  'comb_frequencies': '梳状频率',
  'med_filter_len': 'MED滤波长度',
  'kurtosis_before': 'MED前峭度',
  'kurtosis_after': 'MED后峭度',
  'sidebands': '边频带',
  'mesh_amp': '啮合幅值',
}

const flatItems = computed(() => {
  if (!props.orderAnalysis) return []
  const result = []
  const walk = (obj, prefix = '') => {
    for (const [k, v] of Object.entries(obj)) {
      const displayKey = keyLabelMap[k] || k
      const label = prefix ? `${prefix} / ${displayKey}` : displayKey
      const rawKey = prefix ? `${prefix} / ${k}` : k
      if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
        walk(v, label)
      } else if (!Array.isArray(v)) {
        result.push({ key: rawKey, label, value: v })
      }
    }
  }
  walk(props.orderAnalysis)

  // 如果传入 rotFreq，覆盖历史诊断值
  if (props.rotFreq != null) {
    const rotFreqItem = result.find(item => item.key === 'rot_freq_hz')
    if (rotFreqItem) rotFreqItem.value = props.rotFreq
    const rotRpmItem = result.find(item => item.key === 'rot_rpm')
    if (rotRpmItem) rotRpmItem.value = props.rotRpm ?? (props.rotFreq * 60)
  }

  return result
})

function formatValue(val) {
  if (typeof val === 'number') {
    if (Math.abs(val) < 0.001) return val.toExponential(2)
    if (Math.abs(val) >= 100) return val.toFixed(1)
    return val.toFixed(4)
  }
  return String(val)
}

function isAnomalyKey(key, val) {
  if (typeof val !== 'number') return false
  if (key.includes('_ratio') && val > 0.05) return true
  if (key.includes('_count') && val >= 2) return true
  if (key.includes('_env_ratio') && val > 0.03) return true
  if (key.includes('_order_ratio') && val > 0.03) return true
  return false
}
</script>

<style scoped>
.text-danger {
  color: #f56c6c;
  font-weight: bold;
}
</style>
