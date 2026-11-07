<template>
  <el-row :gutter="16" class="spectrum-row">
    <el-col :span="24">
      <div class="section-header">
        <span class="chart-title">齿轮诊断分析</span>
        <div style="display: flex; align-items: center; gap: 8px;">
          <el-select
            v-if="!computedGear"
            v-model="gearMethod"
            size="small"
            style="width: 140px"
          >
            <el-option label="标准边频带" value="standard" />
            <el-option label="高级指标" value="advanced" />
          </el-select>
          <el-tag v-else type="success" size="small" effect="plain">{{ gearMethodLabel }}</el-tag>
          <el-button
            v-if="!computedGear"
            type="primary"
            size="small"
            :loading="loadingGear"
            @click="$emit('compute')"
          >
            <el-icon><DataAnalysis /></el-icon> 计算
          </el-button>
          <el-button v-else type="info" size="small" @click="$emit('clear')">
            <el-icon><Close /></el-icon> 收起
          </el-button>
        </div>
      </div>
      <div v-if="computedGear && gearData" class="gear-info">
        <el-descriptions :column="4" size="small" border>
          <el-descriptions-item label="SER" v-if="gearData.ser != null">
            <el-tag :type="gearData.ser > 3 ? 'danger' : gearData.ser > 1.5 ? 'warning' : 'success'" size="small">
              {{ gearData.ser.toFixed(3) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="FM0" v-if="gearData.fm0 != null">
            <el-tag :type="gearData.fm0 > 10 ? 'danger' : gearData.fm0 > 5 ? 'warning' : 'success'" size="small">
              {{ gearData.fm0.toFixed(2) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="CAR" v-if="gearData.car != null">
            <el-tag :type="gearData.car > 2 ? 'danger' : gearData.car > 1.2 ? 'warning' : 'success'" size="small">
              {{ gearData.car.toFixed(2) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="转频" v-if="gearData.rot_freq_hz">
            {{ gearData.rot_freq_hz }} Hz / {{ (gearData.rot_freq_hz * 60).toFixed(0) }} RPM
          </el-descriptions-item>
        </el-descriptions>
        <el-table v-if="gearData.sidebands && gearData.sidebands.length > 0" :data="gearData.sidebands" size="small" style="margin-top: 8px;" max-height="200">
          <el-table-column prop="order" label="阶次" width="60" />
          <el-table-column prop="order_low" label="下边频阶次" width="110" />
          <el-table-column prop="order_high" label="上边频阶次" width="110" />
          <el-table-column prop="amp_low" label="下幅值" width="90" />
          <el-table-column prop="amp_high" label="上幅值" width="90" />
          <el-table-column prop="asymmetry" label="不对称度" width="90" />
          <el-table-column label="显著">
            <template #default="{ row }">
              <el-tag :type="row.significant ? 'warning' : 'info'" size="small">
                {{ row.significant ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
        <div v-else style="margin-top: 8px; color: #999; font-size: 13px;">
          未检测到啮合频率参数，无法计算边频带
        </div>
      </div>
      <div v-else-if="loadingGear" class="placeholder">
        <el-skeleton :rows="2" animated />
      </div>
      <div v-else class="placeholder">
        <el-empty description="选择方法后计算齿轮诊断" :image-size="80" />
      </div>
    </el-col>
  </el-row>
</template>

<script setup>
defineProps({
  computedGear: { type: Boolean, default: false },
  loadingGear: { type: Boolean, default: false },
  gearData: { type: Object, default: null },
  gearMethodLabel: { type: String, default: '' },
})

const gearMethod = defineModel('gearMethod', { type: String, default: 'standard' })

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

.gear-info {
  margin-bottom: 8px;
  padding: 12px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 6px;
}
</style>
