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
          <el-button type="primary" @click="handleRefresh">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table :data="alarmList" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="time" label="告警时间" width="180" />
        <el-table-column prop="component" label="故障部件" width="150" />
        <el-table-column prop="faultType" label="故障类型" width="160" />
        <el-table-column label="严重程度" width="120">
          <template #default="{ row }">
            <el-tag :type="getSeverityType(row.severity)">
              {{ getSeverityText(row.severity) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="confidence" label="置信度" width="100" />
        <el-table-column prop="status" label="处理状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button type="primary" link @click="handleDetail(row)">
              查看详情
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
      />
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog v-model="dialogVisible" title="告警详情" width="600px">
      <el-descriptions :column="1" border v-if="selectedAlarm">
        <el-descriptions-item label="告警时间">{{ selectedAlarm.time }}</el-descriptions-item>
        <el-descriptions-item label="故障部件">{{ selectedAlarm.component }}</el-descriptions-item>
        <el-descriptions-item label="故障类型">{{ selectedAlarm.faultType }}</el-descriptions-item>
        <el-descriptions-item label="严重程度">
          <el-tag :type="getSeverityType(selectedAlarm.severity)">
            {{ getSeverityText(selectedAlarm.severity) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="置信度">{{ selectedAlarm.confidence }}</el-descriptions-item>
        <el-descriptions-item label="处理状态">
          <el-tag :type="getStatusType(selectedAlarm.status)">
            {{ selectedAlarm.status }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="dialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getHistoryAlarmList } from '../api'

const loading = ref(false)
const alarmList = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const dialogVisible = ref(false)
const selectedAlarm = ref(null)

const dangerCount = computed(() => alarmList.value.filter(a => a.severity === 'danger').length)
const warnCount = computed(() => alarmList.value.filter(a => a.severity === 'warning').length)
const handledCount = computed(() => alarmList.value.filter(a => a.status === '已处理').length)

const getSeverityType = (severity) => {
  const map = { info: 'info', warning: 'warning', danger: 'danger' }
  return map[severity] || 'info'
}

const getSeverityText = (severity) => {
  const map = { info: '提示', warning: '预警', danger: '严重' }
  return map[severity] || '未知'
}

const getStatusType = (status) => {
  const map = { 待处理: 'warning', 监测中: 'info', 已处理: 'success' }
  return map[status] || 'info'
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await getHistoryAlarmList()
    alarmList.value = res.data.list
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

const handleRefresh = () => {
  loadData()
}

const handleDetail = (row) => {
  selectedAlarm.value = row
  dialogVisible.value = true
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

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
