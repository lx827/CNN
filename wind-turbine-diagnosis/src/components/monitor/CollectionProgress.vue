<template>
  <el-alert
    :title="status"
    type="info"
    :closable="false"
    show-icon
  >
    <template #default>
      <div class="progress-detail">
        <el-progress :percentage="progress" :stroke-width="8" />
        <span class="progress-hint">边端正在按 25600Hz 采集 10s 数据...</span>
      </div>
    </template>
  </el-alert>
</template>

<script setup>
defineProps({
  status: { type: String, default: '' },
  progress: { type: Number, default: 0 },
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
  color: #999;
}
</style>
