<template>
  <el-card>
    <template #header>
      <div class="card-header">
        <span>传感器状态</span>
        <div class="header-actions">
          <el-tag v-if="lastDataSource === 'special'" type="danger" effect="dark" class="special-tag">
            <el-icon><Star-Filled /></el-icon> 特殊采集
          </el-tag>
          <el-select
            :model-value="selectedDevice"
            :disabled="isCollecting || loadingAgents"
            placeholder="选择采集边端"
            aria-label="采集边端"
            style="width: 160px"
            @update:model-value="$emit('update:selectedDevice', $event)"
          >
            <el-option
              v-for="agent in agents"
              :key="agent.id"
              :label="`${agent.name}${agent.online ? '' : '（离线）'}`"
              :value="agent.id"
              :disabled="!agent.online"
            />
          </el-select>
          <el-select
            :model-value="sampleRate"
            :disabled="isCollecting || loadingAgents || !sampleRates.length"
            placeholder="选择采样率"
            aria-label="采样率"
            style="width: 137px"
            @update:model-value="$emit('update:sampleRate', $event)"
          >
            <el-option v-for="rate in sampleRates" :key="rate" :label="`${rate.toLocaleString()} Hz`" :value="rate" />
          </el-select>
          <el-button
            type="primary"
            :loading="isCollecting"
            :disabled="isCollecting || !!collectionUnavailable"
            @click="$emit('collect')"
          >请求采集</el-button>
        </div>
      </div>
      <div class="collection-hint">
        <span v-if="collectionUnavailable">{{ collectionUnavailable }}</span>
        <span v-else>采集时长：{{ collectionDuration ? `${collectionDuration} 秒` : '使用服务端默认值' }}</span>
        <el-button link type="primary" :disabled="isCollecting || loadingAgents" @click="$emit('reloadAgents')">刷新边端</el-button>
      </div>
    </template>
    <el-row :gutter="20">
      <el-col :span="8" v-for="(sensor, index) in sensors" :key="index">
        <div class="sensor-item">
          <div class="indicator" :class="sensor.status"></div>
          <div class="sensor-info">
            <div class="sensor-name">{{ sensor.name }}</div>
            <div class="sensor-status">诊断：{{ sensor.statusText }}<span v-if="sensor.is_offline"> · 设备离线</span></div>
          </div>
        </div>
      </el-col>
    </el-row>
  </el-card>
</template>

<script setup>
defineProps({
  sensors: { type: Array, default: () => [] },
  agents: { type: Array, default: () => [] },
  loadingAgents: { type: Boolean, default: false },
  selectedDevice: { type: String, default: '' },
  sampleRate: { type: Number, default: null },
  sampleRates: { type: Array, default: () => [] },
  isCollecting: { type: Boolean, default: false },
  collectionUnavailable: { type: String, default: '' },
  collectionDuration: { type: Number, default: null },
  lastDataSource: { type: String, default: 'normal' },
})

defineEmits(['update:selectedDevice', 'update:sampleRate', 'collect', 'reloadAgents'])
</script>

<style scoped>
.card-header,
.header-actions {
  flex-wrap: wrap;
}

.header-actions,
.collection-hint {
  display: flex;
  align-items: center;
  gap: 12px;
}

.collection-hint {
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.special-tag {
  font-weight: 600;
}

.sensor-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg-subtle);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  margin-bottom: 12px;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}

.sensor-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.indicator {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--text-placeholder);
}

.indicator.success {
  background: var(--color-success);
}

.indicator.warning {
  background: var(--color-warning);
  box-shadow: 0 0 8px color-mix(in srgb, var(--color-warning) 50%, transparent);
}

.indicator.danger {
  background: var(--color-danger);
  box-shadow: 0 0 8px color-mix(in srgb, var(--color-danger) 50%, transparent);
}

.sensor-info {
  flex: 1;
  min-width: 0;
}

.sensor-name {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.sensor-status {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}
</style>
