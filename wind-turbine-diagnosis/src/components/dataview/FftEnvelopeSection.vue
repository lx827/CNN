<template>
  <el-row :gutter="16" class="spectrum-row">
    <el-col :xs="24" :md="12">
      <div class="section-header">
        <span class="chart-title">FFT 频谱</span>
        <el-button
          v-if="!computedFFT"
          type="primary"
          size="small"
          :loading="loadingFFT"
          @click="$emit('compute-fft')"
        >
          <el-icon><DataAnalysis /></el-icon> 计算 FFT
        </el-button>
        <el-button v-else type="info" size="small" @click="$emit('clear-fft')">
          <el-icon><Close /></el-icon> 收起
        </el-button>
      </div>
      <VibrationChart v-if="computedFFT" :option="fftOption" />
      <div v-else-if="loadingFFT" class="placeholder">
        <el-skeleton :rows="3" animated />
      </div>
      <div v-else class="placeholder">
        <el-empty description="点击按钮计算 FFT 频谱" :image-size="80" />
      </div>
    </el-col>

    <!-- 包络谱 -->
    <el-col :xs="24" :md="12">
      <div class="section-header">
        <span class="chart-title">包络谱（轴承诊断）</span>
        <div style="display: flex; align-items: center; gap: 8px;">
          <el-select
            v-if="!computedEnvelope"
            v-model="envelopeMethod"
            size="small"
            style="width: 150px"
          >
            <el-option label="标准包络" value="envelope" />
            <el-option label="快速峭度图" value="kurtogram" />
            <el-option label="CPW+包络" value="cpw" />
            <el-option label="TEO+包络" value="teager" />
            <el-option label="谱峭度包络" value="spectral_kurtosis" />
            <el-option label="MED+包络" value="med" />
            <el-option label="谱相关/谱相干" value="sc_scoh" />
            <el-option label="MCKD增强包络" value="mckd" />
            <el-option label="WP包络" value="wp" />
            <el-option label="DWT包络" value="dwt" />
            <el-option label="EMD包络" value="emd_envelope" />
            <el-option label="CEEMDAN包络" value="ceemdan_envelope" />
            <el-option label="VMD包络" value="vmd_envelope" />
          </el-select>
          <el-tag v-if="computedEnvelope" type="success" size="small" effect="plain">{{ envelopeMethodLabel }}</el-tag>
          <el-button
            v-if="!computedEnvelope"
            type="primary"
            size="small"
            :loading="loadingEnvelope"
            @click="$emit('compute-envelope')"
          >
            <el-icon><DataAnalysis /></el-icon> 计算
          </el-button>
          <el-button v-else type="info" size="small" @click="$emit('clear-envelope')">
            <el-icon><Close /></el-icon> 收起
          </el-button>
        </div>
      </div>
      <div v-if="computedEnvelope && envelopeData" class="envelope-info">
        <el-tag v-if="envelopeData.optimal_fc" type="info" size="small" effect="plain">
          最优频段 {{ envelopeData.optimal_fc }}±{{ (envelopeData.optimal_bw/2).toFixed(0) }} Hz
        </el-tag>
        <el-tag v-if="envelopeData.max_kurtosis != null" type="info" size="small" effect="plain" style="margin-left: 8px;">
          峭度 {{ envelopeData.max_kurtosis.toFixed(2) }}
        </el-tag>
        <el-tag v-if="envelopeData.kurtosis_after != null" type="info" size="small" effect="plain" style="margin-left: 8px;">
          MED后峭度 {{ envelopeData.kurtosis_after.toFixed(2) }}
        </el-tag>
        <el-tag v-if="envelopeData.teager_rms != null" type="info" size="small" effect="plain" style="margin-left: 8px;">
          TEO RMS {{ envelopeData.teager_rms.toFixed(4) }}
        </el-tag>
        <el-tag v-if="envelopeData.reweighted_score != null" type="info" size="small" effect="plain" style="margin-left: 8px;">
          SK评分 {{ envelopeData.reweighted_score.toFixed(2) }}
        </el-tag>
      </div>
      <VibrationChart v-if="computedEnvelope" :option="envelopeOption" />
      <div v-else-if="loadingEnvelope" class="placeholder">
        <el-skeleton :rows="3" animated />
      </div>
      <div v-else class="placeholder">
        <el-empty description="选择方法后计算包络谱" :image-size="80" />
      </div>
    </el-col>
  </el-row>
</template>

<script setup>
import VibrationChart from '../../components/charts/VibrationChart.vue'

defineProps({
  computedFFT: { type: Boolean, default: false },
  loadingFFT: { type: Boolean, default: false },
  fftOption: { type: Object, default: null },
  computedEnvelope: { type: Boolean, default: false },
  loadingEnvelope: { type: Boolean, default: false },
  envelopeData: { type: Object, default: null },
  envelopeOption: { type: Object, default: null },
  envelopeMethodLabel: { type: String, default: '' },
})

const envelopeMethod = defineModel('envelopeMethod', { type: String, default: 'envelope' })

defineEmits(['compute-fft', 'clear-fft', 'compute-envelope', 'clear-envelope'])
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

.envelope-info {
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
</style>
