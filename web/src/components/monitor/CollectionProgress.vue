<template>
  <el-alert
    :title="status"
    :type="type"
    :closable="false"
    show-icon
    role="status"
  >
    <template v-if="details || progress != null" #default>
      <div class="progress-detail">
        <span v-if="details" class="progress-hint">{{ details }}</span>
        <el-progress v-if="progress != null" :percentage="progress" :stroke-width="8" />
      </div>
    </template>
  </el-alert>
</template>

<script setup>
defineProps({
  status: { type: String, default: '' },
  type: { type: String, default: 'info' },
  details: { type: String, default: '' },
  progress: { type: Number, default: null },
})
</script>

<style scoped>
.progress-detail {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.progress-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

:deep(.el-alert) {
  border-radius: var(--radius-md);
}
</style>
