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
        shadow="never"
        @click="$emit('select', dev)"
      >
        <div class="device-header">
          <div class="device-id">{{ dev.deviceId }}</div>
          <el-tag :type="getDiagnosisView(dev).tagType" size="small" effect="light" round>
            {{ getDiagnosisView(dev).label }}
          </el-tag>
        </div>
        <div class="device-name">{{ dev.deviceName }}</div>
        <div class="device-location">{{ dev.location }}</div>
        <el-text v-if="dev.coverage === 'partial'" type="info" size="small">仅部分对象形成有效评估</el-text>
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
            :stroke-width="10"
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
  margin-bottom: 16px;
}

.device-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

.device-card.active {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--brand-100);
}

.device-card.offline {
  opacity: 0.65;
  background: var(--bg-subtle);
}

.device-card.offline .device-name,
.device-card.offline .device-location {
  color: var(--text-secondary);
}

.offline-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-info);
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
  color: var(--text-primary);
}

.device-name {
  font-size: 14px;
  color: var(--text-regular);
  margin-bottom: 2px;
}

.device-location {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 14px;
}

.health-section {
  margin-bottom: 12px;
}

.health-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.device-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--text-secondary);
  border-top: 1px solid var(--border-light);
  padding-top: 10px;
}

.device-footer span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.fault-hint {
  color: var(--color-danger);
  font-weight: 600;
}

.offline-health {
  font-size: 13px;
  color: var(--color-info);
}
</style>
