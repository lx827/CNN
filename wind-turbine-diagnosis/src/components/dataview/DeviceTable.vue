<template>
  <el-card class="table-card">
    <el-table
      :data="data"
      style="width: 100%"
      v-loading="loading"
      row-key="device_id"
      border
    >
      <el-table-column prop="device_id" label="设备ID" width="140" />
      <el-table-column prop="device_name" label="设备名称" width="160" />
      <el-table-column label="历史数据批次" min-width="400">
        <template #default="{ row }">
          <div class="batch-tags">
            <el-tooltip
              v-for="batch in row.batches"
              :key="batch.batch_index"
              placement="top"
            >
              <template #content>
                <div style="max-width: 200px">
                  <div>状态: <b>{{ getStatusText(batch.diagnosis_status) }}</b></div>
                  <div v-if="batch.health_score != null">健康度: {{ batch.health_score }} 分</div>
                  <div v-if="batch.top_fault">主要异常: {{ batch.top_fault }}</div>
                  <div v-else-if="batch.diagnosis_status">暂无明细故障</div>
                </div>
              </template>
              <el-tag
                :type="getBatchTagType(batch)"
                class="batch-tag"
                :class="{ active: isSelected(row.device_id, batch.batch_index) }"
                @click="$emit('select-batch', row, batch)"
                size="small"
                effect="light"
              >
                #{{ batch.batch_index }} {{ formatTime(batch.created_at) }}
                <el-icon v-if="batch.is_special" class="special-icon"><Star-Filled /></el-icon>
              </el-tag>
            </el-tooltip>
            <el-text v-if="row.batches.length === 0" type="info" size="small">暂无数据</el-text>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openBatchDeleteDialog(row)">
            批量删除
          </el-button>
          <el-button link type="danger" size="small" @click="onDeleteDeviceSpecial(row.device_id)">
            删除特殊数据
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 批量删除对话框 -->
    <el-dialog v-model="dialogVisible" title="批量删除批次" width="400px">
      <div v-if="deleteTarget">
        <p style="margin-bottom: 12px;">设备：<b>{{ deleteTarget.device_name }}</b></p>
        <p style="margin-bottom: 12px; color: #666; font-size: 13px;">请选择要删除的普通数据批次：</p>
        <el-checkbox-group v-model="deleteSelected">
          <el-checkbox
            v-for="batch in deleteTarget.batches.filter(b => !b.is_special)"
            :key="batch.batch_index"
            :label="batch.batch_index"
          >
            批次 #{{ batch.batch_index }} {{ formatTime(batch.created_at) }}
          </el-checkbox>
        </el-checkbox-group>
        <p v-if="deleteTarget.batches.filter(b => !b.is_special).length === 0" style="color: #999;">该设备没有普通数据批次</p>
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          type="danger"
          :disabled="deleteSelected.length === 0"
          :loading="deleteLoading"
          @click="confirmBatchDelete"
        >
          删除选中的 {{ deleteSelected.length }} 个批次
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteBatch, deleteSpecialBatches } from '../../api'
import { formatTime } from '../../utils/format'
import { getStatusText, getStatusType } from '../../utils/status'

const props = defineProps({
  data: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  selectedDeviceId: { type: String, default: null },
  selectedBatchIndex: { type: Number, default: null },
})

const emit = defineEmits(['select-batch', 'refresh', 'batch-deleted'])

const getBatchTagType = (batch) => {
  return getStatusType(batch.diagnosis_status) || 'info'
}

const isSelected = (deviceId, batchIndex) => {
  return props.selectedDeviceId === deviceId && props.selectedBatchIndex === batchIndex
}

// 批量删除
const dialogVisible = ref(false)
const deleteTarget = ref(null)
const deleteSelected = ref([])
const deleteLoading = ref(false)

const openBatchDeleteDialog = (device) => {
  deleteTarget.value = device
  deleteSelected.value = []
  dialogVisible.value = true
}

const confirmBatchDelete = async () => {
  if (deleteSelected.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${deleteSelected.value.length} 个批次吗？此操作不可恢复。`,
      '确认批量删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    deleteLoading.value = true
    const deviceId = deleteTarget.value.device_id
    for (const batchIndex of deleteSelected.value) {
      await deleteBatch(deviceId, batchIndex)
    }
    ElMessage.success(`已删除 ${deleteSelected.value.length} 个批次`)
    dialogVisible.value = false
    emit('batch-deleted', { deviceId, batchIndexes: [...deleteSelected.value] })
    emit('refresh')
  } catch (e) {
    if (e !== 'cancel') {
      console.error('批量删除失败:', e)
      ElMessage.error('批量删除失败')
    }
  } finally {
    deleteLoading.value = false
  }
}

const onDeleteDeviceSpecial = async (deviceId) => {
  try {
    await ElMessageBox.confirm(
      `确定删除设备 ${deviceId} 的所有特殊数据吗？此操作不可恢复。`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    await deleteSpecialBatches(deviceId)
    ElMessage.success('特殊数据已删除')
    emit('refresh')
  } catch (e) {
    if (e !== 'cancel') {
      console.error('删除失败:', e)
      ElMessage.error('删除失败')
    }
  }
}
</script>

<style scoped>
.table-card {
  margin-bottom: 16px;
}

.batch-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.batch-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.batch-tag:hover {
  transform: scale(1.05);
}

.batch-tag.active {
  box-shadow: 0 0 0 2px #165DFF;
}

.special-icon {
  margin-left: 2px;
  font-size: 10px;
}
</style>
