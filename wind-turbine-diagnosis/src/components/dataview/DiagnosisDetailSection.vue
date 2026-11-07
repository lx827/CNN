<template>
  <el-row :gutter="16" class="spectrum-row">
    <el-col :span="24">
      <div class="section-header">
        <span class="chart-title">🔍 频域/阶次诊断明细</span>
        <div style="display: flex; align-items: center; gap: 8px;">
          <template v-if="!showDetail">
            <el-button
              type="primary"
              size="small"
              :loading="loadingDetail"
              @click="$emit('load')"
            >
              <el-icon><DataAnalysis /></el-icon> 加载诊断明细
            </el-button>
          </template>
          <el-button v-else type="info" size="small" @click="$emit('hide')">
            <el-icon><Close /></el-icon> 收起
          </el-button>
        </div>
      </div>
      <div v-if="showDetail">
        <DiagnosisDetail
          :order-analysis="batch.order_analysis"
          :rot-freq="orderData?.rot_freq ?? batch.rot_freq"
          :rot-rpm="orderData?.rot_rpm ?? (batch.rot_freq ? batch.rot_freq * 60 : null)"
        />
      </div>
      <div v-else class="placeholder">
        <el-empty description="点击按钮加载诊断明细" :image-size="80" />
      </div>
    </el-col>
  </el-row>
</template>

<script setup>
import DiagnosisDetail from '../../components/DiagnosisDetail.vue'

defineProps({
  showDetail: { type: Boolean, default: false },
  loadingDetail: { type: Boolean, default: false },
  batch: { type: Object, required: true },
  orderData: { type: Object, default: null },
})

defineEmits(['load', 'hide'])
</script>

<style scoped>
.spectrum-row {
  margin-top: 16px;
}

.chart-title {
  font-weight: 600;
  font-size: 14px;
  color: #333;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.placeholder {
  height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border-radius: 8px;
}
</style>
