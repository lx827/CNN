<template>
  <el-card>
    <template #header>
      <div class="card-header">
        <span>传感器状态</span>
        <div class="header-actions">
          <el-tag v-if="lastDataSource === 'special'" type="danger" effect="dark" class="special-tag">
            <el-icon><Star-Filled /></el-icon> 特殊采集
          </el-tag>
          <el-select :model-value="selectedDevice" placeholder="选择设备" style="width: 160px" size="default" @update:model-value="$emit('update:selectedDevice', $event)">
            <el-option
              v-for="d in devices"
              :key="d.device_id"
              :label="d.name"
              :value="d.device_id"
            />
          </el-select>
          <el-button
            type="primary"
            :loading="isCollecting"
            :disabled="isCollecting || !selectedDevice"
            @click="$emit('collect')"
          >
            <el-icon v-if="!isCollecting"><Video-Play /></el-icon>
            {{ isCollecting ? collectionStatus : '请求采集' }}
          </el-button>
        </div>
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
  devices: { type: Array, default: () => [] },
  selectedDevice: { type: String, default: '' },
  isCollecting: { type: Boolean, default: false },
  collectionStatus: { type: String, default: '' },
  lastDataSource: { type: String, default: 'normal' },
})

defineEmits(['update:selectedDevice', 'collect'])
</script>

<style scoped>
/* .card-header 使用 global.css 全局工具类，此处不重复定义 */
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
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
