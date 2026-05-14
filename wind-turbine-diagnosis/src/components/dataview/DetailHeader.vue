<template>
  <div class="detail-header">
    <span class="header-info">
      数据详情 — <b>{{ device?.device_name || device?.device_id }}</b>
      批次 <b>{{ batch?.batch_index }}</b>
      <el-tag v-if="batch?.is_special" type="danger" size="small" effect="dark">特殊数据</el-tag>
      <el-tag
        v-if="batch?.diagnosis_status"
        :type="getStatusType(batch.diagnosis_status)"
        size="small"
        effect="dark"
      >
        {{ getStatusText(batch.diagnosis_status) }}
        <span v-if="batch.health_score != null">({{ batch.health_score }}分)</span>
      </el-tag>
      <el-tag type="info" size="small">采样率 {{ batch?.sample_rate || 25600 }} Hz</el-tag>
    </span>
    <div class="detail-actions">
      <el-select
        :model-value="channel"
        style="width: 180px"
        size="small"
        @change="val => $emit('update:channel', val)"
      >
        <el-option
          v-for="i in channelOptions"
          :key="i"
          :label="getChannelName(i)"
          :value="i"
        />
      </el-select>
      <el-select
        :model-value="maxFreq"
        style="width: 120px; margin-left: 8px"
        size="small"
        @change="val => $emit('update:maxFreq', val)"
      >
        <el-option label="1000 Hz" :value="1000" />
        <el-option label="2500 Hz" :value="2500" />
        <el-option label="5000 Hz" :value="5000" />
        <el-option label="8192 Hz" :value="8192" />
      </el-select>
      <el-select
        :model-value="denoiseMethod"
        style="width: 130px; margin-left: 8px"
        size="small"
        @change="val => $emit('update:denoiseMethod', val)"
      >
        <el-option label="无预处理" value="none" />
        <el-option label="小波去噪" value="wavelet" />
        <el-option label="VMD分解" value="vmd" />
      </el-select>
      <el-tooltip content="消除基频漂移导致的线性趋势" placement="top">
        <el-switch
          :model-value="enableDetrend"
          active-text="去趋势"
          inactive-text="原始"
          style="margin-left: 12px"
          @change="val => $emit('update:enableDetrend', val)"
        />
      </el-tooltip>
      <el-button type="primary" size="small" style="margin-left: 8px" @click="$emit('export-csv')">
        <el-icon><Download /></el-icon> 导出 CSV
      </el-button>
      <el-button type="warning" size="small" style="margin-left: 8px" :loading="reanalyzing" @click="$emit('reanalyze')">
        <el-icon><Refresh /></el-icon> 重新诊断
      </el-button>
      <el-button type="danger" size="small" style="margin-left: 8px" @click="$emit('delete-batch')">
        <el-icon><Delete /></el-icon> 删除此批次
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { getStatusText, getStatusType } from '../../utils/status'

const props = defineProps({
  device: { type: Object, default: null },
  batch: { type: Object, default: null },
  channel: { type: Number, default: 1 },
  channelOptions: { type: Array, default: () => [1, 2, 3] },
  maxFreq: { type: Number, default: 5000 },
  denoiseMethod: { type: String, default: 'none' },
  enableDetrend: { type: Boolean, default: false },
  reanalyzing: { type: Boolean, default: false },
})

const emit = defineEmits([
  'update:channel',
  'update:maxFreq',
  'update:denoiseMethod',
  'update:enableDetrend',
  'export-csv',
  'reanalyze',
  'delete-batch',
])

const getChannelName = (chNum) => {
  const names = props.device?.channel_names
  if (names && names[String(chNum)]) {
    return names[String(chNum)]
  }
  const defaults = { 1: '通道1-轴承附近', 2: '通道2-驱动端', 3: '通道3-风扇端' }
  return defaults[chNum] || `通道${chNum}`
}
</script>

<style scoped>
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.header-info {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-actions {
  display: flex;
  align-items: center;
}
</style>
