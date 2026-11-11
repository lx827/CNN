<template>
  <el-row :gutter="16" class="device-cards-row">
    <el-col
      :xs="24" :sm="12" :md="8" :lg="6"
      v-for="dev in devices"
      :key="dev.deviceId"
    >
      <el-card
        class="device-card"
        :class="{ active: selectedId === dev.deviceId, offline: dev.is_offline }"
        shadow="hover"
        @click="$emit('select', dev)"
      >
        <div class="device-header">
          <div class="device-id">{{ dev.deviceId }}</div>
          <el-tag :type="getDiagnosisView(dev).tagType" size="small" effect="dark">
            {{ getDiagnosisView(dev).label }}
          </el-tag>
        </div>
        <div class="device-name">{{ dev.deviceName }}</div>
        <div class="device-location">{{ dev.location }}</div>
        <div v-if="dev.is_offline" class="offline-hint">
          <el-icon><Warning /></el-icon> 已离线
        </div>

        <div class="health-section">
          <div class="health-label">健康度</div>
          <div v-if="getDiagnosisView(dev).scoreText === '-'" class="offline-health">
            暂无有效评分
          </div>
          <el-progress
            v-else
            :percentage="dev.health_score"
            :status="getDiagnosisView(dev).tone === 'danger' ? 'exception' : getDiagnosisView(dev).tone"
            :stroke-width="12"
            :format="(p) => p"
          />
        </div>

        <div class="device-footer">
          <span><el-icon><Clock /></el-icon> {{ dev.runHours }} h</span>
          <span v-if="['danger', 'warning'].includes(getDiagnosisView(dev).tone)" class="fault-hint">
            <el-icon><Warning /></el-icon> 需关注
          </span>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { getDiagnosisView } from '../../utils/diagnosisStatus'

defineProps({
  devices: { type: Array, default: () => [] },
  selectedId: { type: String, default: null },
})

defineEmits(['select'])
</script>

<style scoped>
.device-cards-row {
  margin-bottom: 20px;
}

.device-card {
  cursor: pointer;
  border-radius: 10px;
  transition: all 0.3s;
  margin-bottom: 16px;
}

.device-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.12);
}

.device-card.active {
  border: 2px solid #165DFF;
  box-shadow: 0 0 0 4px rgba(22, 93, 255, 0.1);
}

.device-card.offline {
  opacity: 0.7;
  background: #f5f5f5;
}

.device-card.offline .device-name,
.device-card.offline .device-location {
  color: #999;
}

.offline-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 4px;
}

.device-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.device-id {
  font-size: 16px;
  font-weight: 700;
  color: #333;
}

.device-name {
  font-size: 14px;
  color: #555;
  margin-bottom: 4px;
}

.device-location {
  font-size: 12px;
  color: #999;
  margin-bottom: 16px;
}

.health-section {
  margin-bottom: 12px;
}

.health-label {
  font-size: 12px;
  color: #666;
  margin-bottom: 6px;
}

.device-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #999;
  border-top: 1px solid #f0f0f0;
  padding-top: 10px;
}

.fault-hint {
  color: #F5222D;
  font-weight: 600;
}

.offline-health {
  font-size: 13px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
