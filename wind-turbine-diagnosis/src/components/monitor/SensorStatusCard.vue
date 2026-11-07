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
            <div class="sensor-status">{{ sensor.statusText }}</div>
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
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 16px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.special-tag {
  font-weight: bold;
}

.sensor-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  margin-bottom: 12px;
}

.indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #52C41A;
  box-shadow: 0 0 8px rgba(82, 196, 26, 0.5);
}

.indicator.warning {
  background: #FAAD14;
  box-shadow: 0 0 8px rgba(250, 173, 14, 0.5);
}

.indicator.danger {
  background: #F5222D;
  box-shadow: 0 0 8px rgba(245, 34, 45, 0.5);
}

.sensor-info {
  flex: 1;
}

.sensor-name {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

.sensor-status {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}
</style>
