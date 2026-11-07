<template>
  <el-row :gutter="16" class="spectrum-row">
    <el-col :span="24">
      <div class="section-header">
        <span class="chart-title">统计特征指标</span>
        <div style="display: flex; align-items: center; gap: 8px;">
          <template v-if="!computedStats">
            <el-text type="info" size="small">窗口</el-text>
            <el-input-number
              v-model="statsWindowSize"
              :min="64"
              :max="8192"
              :step="64"
              size="small"
              style="width: 110px"
              controls-position="right"
            />
            <el-text type="info" size="small">步长</el-text>
            <el-input-number
              v-model="statsStep"
              :min="1"
              :max="4096"
              :step="32"
              size="small"
              style="width: 100px"
              controls-position="right"
            />
            <el-button
              type="primary"
              size="small"
              :loading="loadingStats"
              @click="$emit('compute')"
            >
              <el-icon><DataAnalysis /></el-icon> 计算
            </el-button>
          </template>
          <el-button v-else type="info" size="small" @click="$emit('clear')">
            <el-icon><Close /></el-icon> 收起
          </el-button>
        </div>
      </div>
      <div v-if="computedStats && statsData" class="stats-grouped">
        <div v-for="group in statsGroups" :key="group.title" class="stats-group">
          <div class="stats-group-title">{{ group.icon }} {{ group.title }}</div>
          <el-descriptions :column="group.items.length > 4 ? 4 : group.items.length" border size="small">
            <el-descriptions-item v-for="item in group.items" :key="item.key" :label="item.label">
              <span class="stat-value">
                {{ statsData[item.key] !== null && statsData[item.key] !== undefined ? Number(statsData[item.key]).toFixed(item.precision) : '-' }}
              </span>
              <el-text v-if="item.normal" type="info" size="small" class="stat-normal">{{ item.normal }}</el-text>
            </el-descriptions-item>
          </el-descriptions>
        </div>
        <el-text type="info" size="small" style="display: block; margin-top: 8px;">
          加窗参数：窗口大小 {{ statsData.window_params.window_size }} 点，滑动步长 {{ statsData.window_params.step }} 点
        </el-text>
      </div>
      <div v-if="computedStats && statsData?.window_series" style="margin-top: 16px;">
        <div class="chart-title">加窗统计量时序图</div>
        <VibrationChart :option="windowedOption" height="280px" />
      </div>
      <div v-else-if="loadingStats" class="placeholder">
        <el-skeleton :rows="2" animated />
      </div>
      <div v-else class="placeholder">
        <el-empty description="设置窗口参数后点击计算" :image-size="80" />
      </div>
    </el-col>
  </el-row>
</template>

<script setup>
import VibrationChart from '../../components/charts/VibrationChart.vue'
import { statsGroups } from '../../composables/useDataView'

defineProps({
  computedStats: { type: Boolean, default: false },
  loadingStats: { type: Boolean, default: false },
  statsData: { type: Object, default: null },
  windowedOption: { type: Object, default: null },
})

const statsWindowSize = defineModel('statsWindowSize', { type: Number, default: 1024 })
const statsStep = defineModel('statsStep', { type: Number, default: 512 })

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

.stats-grouped {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stats-group {
  border-radius: 8px;
  padding: 12px 16px;
  background: #f5f7fa;
}

.stats-group-title {
  font-weight: 600;
  font-size: 14px;
  color: #1d2129;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #165DFF;
}

.stat-normal {
  margin-left: 6px;
  font-size: 12px;
}
</style>
