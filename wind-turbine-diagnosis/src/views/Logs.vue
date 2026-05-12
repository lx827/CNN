<template>
  <div class="logs-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="title">系统日志</span>
          <div class="actions">
            <el-input-number v-model="lines" :min="50" :max="1000" :step="50" size="small" style="width: 120px; margin-right: 12px;" />
            <el-button type="primary" size="small" @click="fetchLogs" :loading="loading">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <div v-if="error" class="error-alert">
        <el-alert :title="error" type="error" show-icon :closable="false" />
      </div>

      <div class="log-container">
        <pre class="log-content">{{ logs || '暂无日志' }}</pre>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { getSystemLogs } from '../api'

const logs = ref('')
const error = ref('')
const loading = ref(false)
const lines = ref(200)
let timer = null

const fetchLogs = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await getSystemLogs(lines.value)
    const data = res.data || {}
    if (data.error) {
      error.value = data.error
    }
    logs.value = data.logs || ''
  } catch (e) {
    error.value = e.message || '获取日志失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchLogs()
  timer = setInterval(fetchLogs, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.logs-page {
  max-width: 1400px;
  margin: 0 auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-size: 18px;
  font-weight: 600;
}

.actions {
  display: flex;
  align-items: center;
}

.error-alert {
  margin-bottom: 16px;
}

.log-container {
  background: #1e1e1e;
  border-radius: 6px;
  padding: 16px;
  max-height: calc(100vh - 220px);
  overflow: auto;
}

.log-content {
  margin: 0;
  color: #d4d4d4;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
