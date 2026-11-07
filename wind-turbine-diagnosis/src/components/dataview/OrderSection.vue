<template>
  <el-row :gutter="16" class="spectrum-row">
    <el-col :span="24">
      <div class="section-header">
        <span class="chart-title">阶次谱（阶次跟踪）</span>
        <div style="display: flex; align-items: center; gap: 8px;">
          <template v-if="!computedOrder">
            <el-text type="info" size="small">转频范围</el-text>
            <el-input-number
              v-model="orderFreqMin"
              :min="1"
              :max="500"
              :step="5"
              size="small"
              style="width: 90px"
              controls-position="right"
            />
            <el-text type="info" size="small">~</el-text>
            <el-input-number
              v-model="orderFreqMax"
              :min="1"
              :max="500"
              :step="5"
              size="small"
              style="width: 90px"
              controls-position="right"
            />
            <el-text type="info" size="small">Hz</el-text>
            <el-text type="info" size="small" style="margin-left: 4px">每转采样</el-text>
            <el-input-number
              v-model="orderSamplesPerRev"
              :min="64"
              :max="4096"
              :step="64"
              size="small"
              style="width: 100px"
              controls-position="right"
            />
            <el-button
              type="primary"
              size="small"
              :loading="loadingOrder"
              @click="$emit('compute')"
            >
              <el-icon><DataAnalysis /></el-icon> 计算阶次谱
            </el-button>
          </template>
          <el-button v-else type="info" size="small" @click="$emit('clear')">
            <el-icon><Close /></el-icon> 收起
          </el-button>
        </div>
      </div>
      <div v-if="computedOrder && orderData" class="order-info">
        <el-tag type="success" size="small" effect="plain">
          估计转速 {{ orderData.rot_rpm }} RPM（转频 {{ orderData.rot_freq }} Hz）
        </el-tag>
        <el-tag type="info" size="small" effect="plain" style="margin-left: 8px;">
          每转 {{ orderData.samples_per_rev }} 点
        </el-tag>
      </div>
      <VibrationChart v-if="computedOrder" :option="orderOption" />
      <div v-else-if="loadingOrder" class="placeholder">
        <el-skeleton :rows="3" animated />
      </div>
      <div v-else class="placeholder">
        <el-empty description="设置转频搜索范围后计算阶次谱" :image-size="80" />
      </div>
    </el-col>
  </el-row>
</template>

<script setup>
import VibrationChart from '../../components/charts/VibrationChart.vue'

defineProps({
  computedOrder: { type: Boolean, default: false },
  loadingOrder: { type: Boolean, default: false },
  orderData: { type: Object, default: null },
  orderOption: { type: Object, default: null },
})

const orderFreqMin = defineModel('orderFreqMin', { type: Number, default: 10 })
const orderFreqMax = defineModel('orderFreqMax', { type: Number, default: 100 })
const orderSamplesPerRev = defineModel('orderSamplesPerRev', { type: Number, default: 1024 })

defineEmits(['compute', 'clear'])
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

.order-info {
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 6px;
}
</style>
