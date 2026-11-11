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
        <el-tag :type="getDiagnosisView(gearData).tagType">齿轮诊断：{{ getDiagnosisView(gearData).label }}</el-tag>
        <DiagnosisCoverage :result="gearData" />
        <el-alert
          v-if="gearData.tsa_status === 'not_evaluable' || unavailableMetricReason"
          :title="unavailableMetricReason || gearData.tsa_reason"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 8px;"
        />
        <el-descriptions :column="4" size="small" border>
          <el-descriptions-item label="SER" v-if="gearData.ser != null">
            <el-tag :type="indicatorType('ser')" size="small">
              {{ gearData.ser.toFixed(3) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="FM0" v-if="gearData.fm0 != null">
            <el-tag :type="indicatorType('fm0')" size="small">
              {{ gearData.fm0.toFixed(2) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="CAR" v-if="gearData.car != null">
            <el-tag :type="indicatorType('car')" size="small">
              {{ gearData.car.toFixed(2) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="FM4" v-if="gearData.fm4 != null">
            <el-tag :type="indicatorType('fm4')" size="small">{{ gearData.fm4.toFixed(3) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="M6A / M8A" v-if="gearData.m6a != null || gearData.m8a != null">
            {{ formatRaw(gearData.m6a) }} / {{ formatRaw(gearData.m8a) }}（仅原始值）
          </el-descriptions-item>
          <el-descriptions-item label="NA4 / NB4" v-if="gearData.na4 != null || gearData.nb4 != null">
            {{ formatRaw(gearData.na4) }} / {{ formatRaw(gearData.nb4) }}（仅原始值）
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
          {{ unavailableMetricReason || '未配置啮合频率参数，无法计算边频带；不可评估不表示健康' }}
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
import { computed } from 'vue'
import { getDiagnosisView } from '../../utils/diagnosisStatus'
import DiagnosisCoverage from '../DiagnosisCoverage.vue'

const props = defineProps({
  computedGear: { type: Boolean, default: false },
  loadingGear: { type: Boolean, default: false },
  gearData: { type: Object, default: null },
  gearMethodLabel: { type: String, default: '' },
})

const gearMethod = defineModel('gearMethod', { type: String, default: 'standard' })

const indicatorType = (name) => {
  const indicator = props.gearData?.fault_indicators?.[name]
  if (indicator?.critical) return 'danger'
  if (indicator?.warning) return 'warning'
  return 'info'
}

const formatRaw = (value) => value == null ? '不可评估' : Number(value).toFixed(3)

const unavailableMetricReason = computed(() => {
  const metrics = props.gearData?.metrics || {}
  const unavailable = Object.values(metrics).find(metric => metric?.status === 'not_evaluable' && metric.reason !== 'tsa_not_requested')
  if (!unavailable) return ''
  const reasons = {
    missing_fixed_axis_geometry: '未配置定轴输入轮齿数',
    missing_comparable_residual_history: 'NA4 缺少可比历史 residual 方差，未计算',
    missing_comparable_envelope_history: 'NB4 缺少可比历史包络方差，未计算',
    car_requires_accurate_constant_speed: 'CAR 要求准确恒速，当前工况不评估',
    tsa_requires_accurate_constant_speed_with_continuous_phase: 'TSA 要求准确恒速连续相位，当前仅保留可用频谱指标',
    requested_mesh_or_sidebands_above_order_coverage: '啮合或边带超出阶次谱覆盖，SER 不可评估',
  }
  return reasons[unavailable.reason] || `指标不可评估：${unavailable.reason}`
})

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
