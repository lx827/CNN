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
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 16px;
}

.params {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.param-item {
  text-align: center;
  padding: 16px;
  background: linear-gradient(135deg, #165DFF15, #0E42D215);
  border-radius: 8px;
}

.param-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.param-value {
  font-size: 28px;
  font-weight: bold;
  color: #165DFF;
}

.unit {
  font-size: 14px;
  color: #999;
}
</style>
