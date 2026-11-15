<template>
  <el-row :gutter="16" class="summary-row">
    <el-col v-for="card in cards" :key="card.label" :xs="12" :sm="8" :md="8" :lg="4">
      <el-card class="summary-card" shadow="never">
        <div class="card-content">
          <div class="icon-wrap" :style="{ background: card.soft, color: card.color }">
            <el-icon :size="22"><component :is="card.icon" /></el-icon>
          </div>
          <div class="card-info">
            <div class="label">{{ card.label }}</div>
            <div class="value" :style="{ color: card.color }">{{ card.value }}</div>
          </div>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  total: { type: Number, default: 0 },
  normal: { type: Number, default: 0 },
  warning: { type: Number, default: 0 },
  fault: { type: Number, default: 0 },
  offline: { type: Number, default: 0 },
  unknown: { type: Number, default: 0 },
})

const cards = computed(() => [
  { label: '设备总数', value: props.total, icon: 'Cpu', color: 'var(--color-primary)', soft: 'var(--color-primary-soft)' },
  { label: '诊断正常', value: props.normal, icon: 'CircleCheck', color: 'var(--color-success)', soft: 'var(--color-success-soft)' },
  { label: '预警设备', value: props.warning, icon: 'Warning', color: 'var(--color-warning)', soft: 'var(--color-warning-soft)' },
  { label: '故障设备', value: props.fault, icon: 'CircleClose', color: 'var(--color-danger)', soft: 'var(--color-danger-soft)' },
  { label: '离线设备', value: props.offline, icon: 'Connection', color: 'var(--color-info)', soft: 'var(--color-info-soft)' },
  { label: '诊断未知', value: props.unknown, icon: 'QuestionFilled', color: 'var(--text-secondary)', soft: 'var(--bg-subtle)' },
])
</script>

<style scoped>
.summary-row {
  margin-bottom: 20px;
}

.summary-card {
  transition: transform var(--transition-base), box-shadow var(--transition-base);
}

.summary-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
}

.summary-card :deep(.el-card__body) {
  padding: 18px 20px;
}

.card-content {
  display: flex;
  align-items: center;
  gap: 14px;
}

.icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
}

.card-info {
  flex: 1;
  min-width: 0;
}

.card-info .label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-info .value {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}
</style>
