<template>
  <el-row :gutter="16" class="spectrum-row">
    <el-col :span="24">
      <div class="section-header">
        <span class="chart-title">STFT 时频谱</span>
        <div style="display: flex; align-items: center; gap: 8px;">
          <template v-if="!computedSTFT">
            <el-text type="info" size="small">窗口</el-text>
            <el-input-number
              v-model="stftNperseg"
              :min="64"
              :max="4096"
              :step="64"
              size="small"
              style="width: 110px"
              controls-position="right"
            />
            <el-text type="info" size="small">重叠</el-text>
            <el-input-number
              v-model="stftNoverlap"
              :min="0"
              :max="4095"
              :step="32"
              size="small"
              style="width: 110px"
              controls-position="right"
            />
            <el-button
              type="primary"
              size="small"
              :loading="loadingSTFT"
              @click="$emit('compute')"
            >
              <el-icon><DataAnalysis /></el-icon> 计算 STFT
            </el-button>
          </template>
          <el-button v-else type="info" size="small" @click="$emit('clear')">
            <el-icon><Close /></el-icon> 收起
          </el-button>
        </div>
      </div>
      <VibrationChart v-if="computedSTFT" :option="stftOption" height="600px" />
      <div v-else-if="loadingSTFT" class="placeholder">
        <el-skeleton :rows="4" animated />
      </div>
      <div v-else class="placeholder">
        <el-empty description="设置窗口参数后计算 STFT 时频谱" :image-size="80" />
      </div>
    </el-col>
  </el-row>
</template>

<script setup>
import VibrationChart from '../../components/charts/VibrationChart.vue'

defineProps({
  computedSTFT: { type: Boolean, default: false },
  loadingSTFT: { type: Boolean, default: false },
  stftOption: { type: Object, default: null },
})

const stftNperseg = defineModel('stftNperseg', { type: Number, default: 512 })
const stftNoverlap = defineModel('stftNoverlap', { type: Number, default: 256 })

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
</style>
