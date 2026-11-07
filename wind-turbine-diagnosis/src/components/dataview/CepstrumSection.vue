<template>
  <el-row :gutter="16" class="spectrum-row">
    <el-col :span="24">
      <div class="section-header">
        <span class="chart-title">倒谱分析</span>
        <div style="display: flex; align-items: center; gap: 8px;">
          <template v-if="!computedCepstrum">
            <el-text type="info" size="small">最大倒频率</el-text>
            <el-input-number
              v-model="cepstrumMaxQuefrency"
              :min="10"
              :max="2000"
              :step="10"
              size="small"
              style="width: 110px"
              controls-position="right"
            />
            <el-text type="info" size="small">ms</el-text>
            <el-button
              type="primary"
              size="small"
              :loading="loadingCepstrum"
              @click="$emit('compute')"
            >
              <el-icon><DataAnalysis /></el-icon> 计算倒谱
            </el-button>
          </template>
          <el-button v-else type="info" size="small" @click="$emit('clear')">
            <el-icon><Close /></el-icon> 收起
          </el-button>
        </div>
      </div>
      <div v-if="computedCepstrum && cepstrumData" class="cepstrum-info">
        <el-text type="info" size="small" style="white-space: nowrap;">检测到峰值：</el-text>
        <el-tag
          v-for="(peak, idx) in cepstrumData.peaks"
          :key="idx"
          type="warning"
          size="small"
          effect="plain"
        >
          {{ peak.quefrency_ms }} ms → {{ peak.freq_hz }} Hz
        </el-tag>
        <el-text v-if="!cepstrumData.peaks || cepstrumData.peaks.length === 0" type="info" size="small">未检测到显著峰值</el-text>
      </div>
      <VibrationChart v-if="computedCepstrum" :option="cepstrumOption" />
      <div v-else-if="loadingCepstrum" class="placeholder">
        <el-skeleton :rows="3" animated />
      </div>
      <div v-else class="placeholder">
        <el-empty description="点击按钮计算倒谱分析" :image-size="80" />
      </div>
    </el-col>
  </el-row>
</template>

<script setup>
import VibrationChart from '../../components/charts/VibrationChart.vue'

defineProps({
  computedCepstrum: { type: Boolean, default: false },
  loadingCepstrum: { type: Boolean, default: false },
  cepstrumData: { type: Object, default: null },
  cepstrumOption: { type: Object, default: null },
})

const cepstrumMaxQuefrency = defineModel('cepstrumMaxQuefrency', { type: Number, default: 500 })

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

.cepstrum-info {
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f9f0ff;
  border: 1px solid #d3adf7;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
</style>
