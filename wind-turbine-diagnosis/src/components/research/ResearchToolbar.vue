<template>
  <div class="toolbar">
    <div class="selectors">
      <el-select :model-value="selectedDeviceId" placeholder="设备" filterable class="select" @update:model-value="$emit('update:selectedDeviceId', $event)">
        <el-option v-for="device in devices" :key="device.device_id" :label="device.device_name || device.device_id" :value="device.device_id" />
      </el-select>

      <el-select :model-value="selectedBatchIndex" placeholder="批次" filterable class="select small" @update:model-value="$emit('update:selectedBatchIndex', $event)">
        <el-option v-for="batch in batches" :key="batch.batch_index" :label="`#${batch.batch_index}`" :value="batch.batch_index" />
      </el-select>

      <el-select :model-value="selectedChannel" placeholder="通道" class="select small" @update:model-value="$emit('update:selectedChannel', $event)">
        <el-option v-for="ch in channels" :key="ch.value" :label="ch.label" :value="ch.value" />
      </el-select>

      <el-segmented :model-value="runMode" :options="runModeOptions" @update:model-value="$emit('update:runMode', $event)" />

      <el-select v-if="runMode === 'single'" :model-value="selectedMethod" class="select method-select" placeholder="分析方法" filterable @update:model-value="$emit('update:selectedMethod', $event)">
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

      <el-select :model-value="denoise" class="select small" @update:model-value="$emit('update:denoise', $event)">
        <el-option label="不去噪" value="none" />
        <el-option label="小波" value="wavelet" />
        <el-option label="VMD" value="vmd" />
        <el-option label="小波+VMD" value="wavelet_vmd" />
        <el-option label="小波+LMS" value="wavelet_lms" />
        <el-option label="EMD" value="emd" />
        <el-option label="CEEMDAN" value="ceemdan" />
        <el-option label="WP降噪" value="wavelet_packet" />
        <el-option label="CEEMDAN+WP降噪" value="ceemdan_wp" />
        <el-option label="EEMD降噪" value="eemd" />
        <el-option label="S-G" value="savgol" />
      </el-select>

      <el-select v-if="runMode === 'ensemble'" :model-value="profile" class="select small" @update:model-value="$emit('update:profile', $event)">
        <el-option label="运行级" value="runtime" />
        <el-option label="均衡" value="balanced" />
        <el-option label="全量" value="exhaustive" />
      </el-select>
      <el-input-number :model-value="rotFrequency" :min="0.001" :precision="3" placeholder="已知转频 Hz" controls-position="right" @update:model-value="$emit('update:rotFrequency', $event)" />
      <span>已知恒定转频 Hz（留空自动估计）</span>
      <template v-if="runMode !== 'single' || selectedMethod === 'mckd'">
        <el-select :model-value="targetFault" clearable class="select" placeholder="MCKD 目标（空则 MED）" @update:model-value="$emit('update:targetFault', $event)">
          <el-option v-for="fault in ['BPFO', 'BPFI', 'BSF', 'FTF']" :key="fault" :value="fault" :label="fault" />
        </el-select>
      </template>
      <template v-if="runMode !== 'single' || selectedMethod === 'cpw'">
        <el-input :model-value="combFrequencies" class="select" placeholder="稳定梳状基频 Hz，逗号分隔" @update:model-value="$emit('update:combFrequencies', $event)" />
        <el-checkbox :model-value="combIsStable" @update:model-value="$emit('update:combIsStable', $event)">确认整段梳状频率稳定</el-checkbox>
      </template>
    </div>

    <el-button type="primary" :loading="loading" :disabled="!canRun" @click="$emit('run')">
      <el-icon><Cpu /></el-icon>
      <span>{{ runMode === 'single' ? '运行方法' : runMode === 'ensemble' ? '集成诊断' : '运行全部' }}</span>
    </el-button>
    <el-button type="default" @click="$emit('goto-data')">
      <el-icon><DataLine /></el-icon> 查看数据
    </el-button>
  </div>
</template>

<script setup>
import { Cpu, DataLine } from '@element-plus/icons-vue'
import { runModeOptions } from '../../composables/useResearchDiagnosis'

defineProps({
  devices: { type: Array, default: () => [] },
  batches: { type: Array, default: () => [] },
  channels: { type: Array, default: () => [] },
  selectedDeviceId: { type: String, default: '' },
  selectedBatchIndex: { type: Number, default: null },
  selectedChannel: { type: Number, default: 1 },
  runMode: { type: String, default: 'single' },
  selectedMethod: { type: String, default: 'envelope' },
  targetFault: { type: String, default: '' },
  combFrequencies: { type: String, default: '' },
  combIsStable: { type: Boolean, default: false },
  rotFrequency: { type: Number, default: null },
  denoise: { type: String, default: 'none' },
  profile: { type: String, default: 'balanced' },
  bearingMethodGroup: { type: Array, default: () => [] },
  gearMethodGroup: { type: Array, default: () => [] },
  planetaryMethodGroup: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  canRun: { type: Boolean, default: false },
})

defineEmits(['update:selectedDeviceId', 'update:selectedBatchIndex', 'update:selectedChannel', 'update:runMode', 'update:selectedMethod', 'update:denoise', 'update:profile', 'update:targetFault', 'update:combFrequencies', 'update:combIsStable', 'update:rotFrequency', 'run', 'goto-data'])
</script>

<style scoped>
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

@media (max-width: 1100px) {
  .toolbar { align-items: stretch; flex-direction: column; }
  .select, .select.small, .method-select { width: 100%; }
}
</style>
