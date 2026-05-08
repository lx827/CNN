<template>
  <div class="alarm">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="24" :sm="8">
        <el-card class="stat-card danger">
          <div class="stat-content">
            <el-icon :size="40"><CircleClose /></el-icon>
            <div class="stat-info">
              <div class="stat-value">{{ dangerCount }}</div>
              <div class="stat-label">严重告警</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card class="stat-card warning">
          <div class="stat-content">
            <el-icon :size="40"><Warning /></el-icon>
            <div class="stat-info">
              <div class="stat-value">{{ warnCount }}</div>
              <div class="stat-label">预警信息</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card class="stat-card success">
          <div class="stat-content">
            <el-icon :size="40"><CircleCheck /></el-icon>
            <div class="stat-info">
              <div class="stat-value">{{ handledCount }}</div>
              <div class="stat-label">已处理</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 告警列表 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span>告警记录列表</span>
          <div class="header-actions">
            <el-radio-group v-model="filterLevel" size="small" @change="onFilterChange">
              <el-radio-button label="">全部</el-radio-button>
              <el-radio-button label="warning">预警</el-radio-button>
              <el-radio-button label="critical">严重</el-radio-button>
            </el-radio-group>
            <el-button type="primary" size="small" @click="handleRefresh">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="alarmList" stripe v-loading="loading">
        <el-table-column prop="time" label="告警时间" width="170" />
        <el-table-column prop="device_id" label="设备" width="110" />
        <el-table-column label="通道" width="140">
          <template #default="{ row }">
            <el-tag v-if="row.channel" size="small" type="info">
              {{ row.channel_name || `通道${row.channel}` }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="类别" width="110">
          <template #default="{ row }">
            <el-tag size="small">{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="告警标题" min-width="220" show-overflow-tooltip />
        <el-table-column label="级别" width="90">
          <template #default="{ row }">
            <el-tag :type="getLevelType(row.level)">
              {{ getLevelText(row.level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleDetail(row)">
              详情
            </el-button>
            <el-button
              v-if="!row.is_resolved"
              type="success"
              link
              size="small"
              @click="handleResolve(row)"
            >
              标记处理
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        class="pagination"
        @current-change="handlePageChange"
      />
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog v-model="dialogVisible" title="告警详情" width="640px">
      <el-descriptions :column="1" border v-if="selectedAlarm">
        <el-descriptions-item label="告警时间">{{ selectedAlarm.time }}</el-descriptions-item>
        <el-descriptions-item label="设备">{{ selectedAlarm.device_id }}</el-descriptions-item>
        <el-descriptions-item label="通道">
          <el-tag v-if="selectedAlarm.channel" size="small" type="info">
            {{ selectedAlarm.channel_name || `通道${selectedAlarm.channel}` }}
          </el-tag>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="类别">{{ selectedAlarm.category }}</el-descriptions-item>
        <el-descriptions-item label="告警标题">{{ selectedAlarm.title }}</el-descriptions-item>
        <el-descriptions-item label="级别">
          <el-tag :type="getLevelType(selectedAlarm.level)">
            {{ getLevelText(selectedAlarm.level) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="详细描述">
          <div style="white-space: pre-wrap; line-height: 1.6;">{{ selectedAlarm.description }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="处理建议">
          <div style="white-space: pre-wrap; line-height: 1.6;">{{ selectedAlarm.suggestion }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="处理状态">
          <el-tag :type="getStatusType(selectedAlarm.status)">
            {{ selectedAlarm.status }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="dialogVisible = false">关闭</el-button>
        <el-button
          v-if="selectedAlarm && !selectedAlarm.is_resolved"
          type="success"
          @click="handleResolveFromDialog"
        >
          标记为已处理
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getHistoryAlarmList, updateAlarmStatus } from '../api'

const loading = ref(false)
const alarmList = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const filterLevel = ref('')
const dialogVisible = ref(false)
const selectedAlarm = ref(null)

const dangerCount = computed(() => alarmList.value.filter(a => a.level === 'critical').length)
const warnCount = computed(() => alarmList.value.filter(a => a.level === 'warning').length)
const handledCount = computed(() => alarmList.value.filter(a => a.is_resolved).length)

const getLevelType = (level) => {
  const map = { info: 'info', warning: 'warning', critical: 'danger' }
  return map[level] || 'info'
}

const getLevelText = (level) => {
  const map = { info: '提示', warning: '预警', critical: '严重' }
  return map[level] || '未知'
}

const getStatusType = (status) => {
  const map = { 待处理: 'warning', 已处理: 'success' }
  return map[status] || 'info'
}

const loadData = async () => {
  loading.value = true
  try {
    const filters = {}
    if (filterLevel.value) filters.level = filterLevel.value
    const res = await getHistoryAlarmList(currentPage.value, pageSize.value, filters)
    alarmList.value = res.data.list
    total.value = res.data.total
  } catch (e) {
    console.error('加载告警失败:', e)
    ElMessage.error('加载告警失败')
  } finally {
    loading.value = false
  }
}

const onFilterChange = () => {
  currentPage.value = 1
  loadData()
}

const handlePageChange = (page) => {
  currentPage.value = page
  loadData()
}

const handleRefresh = () => {
  loadData()
}

const handleDetail = (row) => {
  selectedAlarm.value = row
  dialogVisible.value = true
}

const handleResolve = async (row) => {
  try {
    await ElMessageBox.confirm('确认标记该告警为已处理？', '提示', { type: 'warning' })
    await updateAlarmStatus(row.id)
    ElMessage.success('已标记为处理')
    loadData()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('处理告警失败:', e)
      ElMessage.error('处理失败')
    }
  }
}

const handleResolveFromDialog = async () => {
  if (!selectedAlarm.value) return
  await updateAlarmStatus(selectedAlarm.value.id)
  ElMessage.success('已标记为处理')
  dialogVisible.value = false
  loadData()
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.alarm {
  padding: 0;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  border-radius: 8px;
  margin-bottom: 20px;
}

.stat-card.danger {
  background: linear-gradient(135deg, #fff1f0, #ffccc7);
  border: 1px solid #ffa39e;
}

.stat-card.warning {
  background: linear-gradient(135deg, #fffbe6, #ffe58f);
  border: 1px solid #ffd666;
}

.stat-card.success {
  background: linear-gradient(135deg, #f6ffed, #b7eb8f);
  border: 1px solid #95de64;
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 20px;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: #333;
}

.stat-label {
  font-size: 14px;
  color: #666;
  margin-top: 4px;
}

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

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
