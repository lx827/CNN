<template>
  <div class="research-diagnosis">
    <!-- 工具栏 -->
    <ResearchToolbar
      v-model:selected-device-id="selectedDeviceId"
      v-model:selected-batch-index="selectedBatchIndex"
      v-model:selected-channel="selectedChannel"
      v-model:run-mode="runMode"
      v-model:selected-method="selectedMethod"
      v-model:denoise="denoise"
      v-model:profile="profile"
      v-model:target-fault="targetFault"
      v-model:comb-frequencies="combFrequencies"
      v-model:comb-is-stable="combIsStable"
      v-model:rot-frequency="rotFrequency"
      v-model:composite-alignment="compositeAlignment"
      :devices="devices"
      :batches="currentBatches"
      :channels="currentChannels"
      :bearing-method-group="bearingMethodGroup"
      :gear-method-group="gearMethodGroup"
      :planetary-method-group="planetaryMethodGroup"
      :composite-method-group="compositeMethodGroup"
      :loading="loading"
      :can-run="canRun"
      @run="runAnalysis"
      @goto-data="gotoDataView"
    />

    <!-- 方法说明提示 -->
    <div v-if="runMode === 'single' && selectedMethodInfo" class="method-desc-card">
      <el-tag :type="methodCategoryTag" size="small">{{ selectedMethodInfo.label }}</el-tag>
      <span class="method-desc-text">{{ selectedMethodInfo.description }}</span>
    </div>

    <!-- 全方法/集成诊断摘要 -->
    <div v-if="result && runMode !== 'single'" class="summary-band">
      <div class="metric">
        <span class="label">状态</span>
        <el-tag :type="getDiagnosisView(result).tagType" size="large">{{ getDiagnosisView(result).text }}</el-tag>
      </div>
      <div class="metric"><span class="label">健康度</span><strong>{{ getDiagnosisView(result).scoreText }}</strong></div>
      <div class="metric"><span class="label">评估覆盖</span><strong>{{ coverageText(result.coverage) }}</strong></div>
      <div class="metric"><span class="label">转频</span><strong>{{ result.rot_freq_hz ?? '-' }} Hz</strong></div>
    </div>

    <!-- 单方法结果摘要 -->
    <div v-if="result && runMode === 'single'" class="summary-band">
      <div class="metric">
        <span class="label">方法</span>
        <el-tag :type="methodCategoryTag" size="large">{{ result.requested_method ? result.method.toUpperCase() + '（' + result.requested_method.toUpperCase() + ' 未指定目标）' : selectedMethodInfo?.label || selectedMethod }}</el-tag>
      </div>
      <div class="metric"><span class="label">转频</span><strong>{{ result.rot_freq_hz ?? '-' }} Hz</strong></div>
      <div class="metric" v-if="result.health_score != null"><span class="label">健康度</span><strong>{{ getDiagnosisView(result).scoreText }}</strong></div>
      <div class="metric" v-if="selectedMethodInfo?.category === 'composite'">
        <span class="label">诊断结论</span><el-tag type="info">未知 · 仅供研究</el-tag>
      </div>
      <div class="metric" v-else-if="selectedMethodInfo?.category === 'bearing' || result.is_planetary">
        <span class="label">方法评估</span>
        <el-tag :type="evaluationStatusType(result.evaluation_status)">
          {{ evaluationStatusText(result.evaluation_status) }}
        </el-tag>
      </div>
      <div class="metric" v-else-if="result.evaluation_status"><span class="label">诊断结论</span><el-tag :type="getDiagnosisView(result).tagType">{{ getDiagnosisView(result).text }}</el-tag></div>
    </div>

    <el-empty v-if="!result && !loading" :description="runMode === 'single' ? '请选择分析方法后运行' : '请点击运行开始诊断'" />

    <!-- ========== 单方法结果详情 ========== -->
    <SingleResultPanels
      v-if="result && runMode === 'single'"
      :result="result"
      :selected-method-info="selectedMethodInfo"
    />

    <!-- ========== 全方法/集成诊断结果详情 ========== -->
    <EnsembleResultPanels
      v-if="result && runMode !== 'single'"
      :result="result"
    />
  </div>
</template>

<script setup>
import ResearchToolbar from '../components/research/ResearchToolbar.vue'
import SingleResultPanels from '../components/research/SingleResultPanels.vue'
import EnsembleResultPanels from '../components/research/EnsembleResultPanels.vue'
import { useResearchDiagnosis } from '../composables/useResearchDiagnosis'
import { evaluationStatusType, evaluationStatusText } from '../utils/researchDisplay'
import { getDiagnosisView } from '../utils/diagnosisStatus'
const coverageText = value => ({ complete: '完整', partial: '部分', none: '无有效证据' })[value] || '未知'

const {
  devices, selectedDeviceId, selectedBatchIndex, selectedChannel,
  runMode, selectedMethod, denoise, profile, loading, result,
  targetFault, combFrequencies, combIsStable, rotFrequency, compositeAlignment,
  currentBatches, currentChannels, canRun,
  bearingMethodGroup, gearMethodGroup, planetaryMethodGroup, compositeMethodGroup,
  selectedMethodInfo, methodCategoryTag,
  runAnalysis, gotoDataView,
} = useResearchDiagnosis()
</script>

<style scoped>
.research-diagnosis {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.method-desc-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #f0f9ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
}

.method-desc-text {
  color: #475569;
  font-size: 14px;
  line-height: 1.5;
}

.summary-band {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  padding: 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.metric {
  min-height: 68px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}

.label { color: #6b7280; font-size: 13px; }
.metric strong { font-size: 20px; color: #111827; }

.fault-label-metric {
  grid-column: 1 / -1;
  min-height: auto;
}
.fault-label-text {
  font-size: 16px !important;
  word-break: break-all;
}

@media (max-width: 1100px) {
  .summary-band { grid-template-columns: 1fr; }
}
</style>
