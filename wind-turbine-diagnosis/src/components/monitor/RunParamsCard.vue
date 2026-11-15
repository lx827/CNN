<template>
  <el-card>
    <template #header>
      <div class="card-header">
        <span>运行参数</span>
        <el-select :model-value="modelValue" placeholder="选择设备" style="width: 160px" size="small" @update:model-value="$emit('update:modelValue', $event)" @change="$emit('change')">
          <el-option
            v-for="d in devices"
            :key="d.device_id"
            :label="d.name"
            :value="d.device_id"
          />
        </el-select>
      </div>
    </template>
    <div class="params">
      <div class="param-item">
        <div class="param-label">转速</div>
        <div class="param-value">
          {{ params.rpm != null ? params.rpm.toFixed(1) : '-' }}
          <span v-if="params.rpm != null" class="unit">RPM</span>
        </div>
      </div>
      <div class="param-item">
        <div class="param-label">转速 <el-tag type="warning" size="small" effect="plain">估计</el-tag></div>
        <div class="param-value">
          {{ params.estimated_rpm != null ? params.estimated_rpm.toFixed(1) : '-' }}
          <span v-if="params.estimated_rpm != null" class="unit">RPM</span>
        </div>
      </div>
      <div class="param-item">
        <div class="param-label">温度</div>
        <div class="param-value">
          {{ params.temperature != null ? params.temperature.toFixed(1) : '-' }}
          <span v-if="params.temperature != null" class="unit">°C</span>
        </div>
      </div>
      <div class="param-item">
        <div class="param-label">负载</div>
        <div class="param-value">
          {{ params.load != null ? params.load.toFixed(1) : '-' }}
          <span v-if="params.load != null" class="unit">%</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
defineProps({
  params: { type: Object, default: () => ({}) },
  devices: { type: Array, default: () => [] },
  modelValue: { type: String, default: '' },
})

defineEmits(['update:modelValue', 'change'])
</script>

<style scoped>
/* .card-header 使用 global.css 全局工具类，此处不重复定义 */
.params {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.param-item {
  text-align: center;
  padding: 14px 16px;
  background: var(--color-primary-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}

.param-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.param-label {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.param-value {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--color-primary);
  font-variant-numeric: tabular-nums;
}

.unit {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-left: 2px;
}
</style>
