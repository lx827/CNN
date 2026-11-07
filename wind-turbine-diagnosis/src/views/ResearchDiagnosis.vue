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
      :devices="devices"
      :batches="currentBatches"
      :channels="currentChannels"
      :bearing-method-group="bearingMethodGroup"
      :gear-method-group="gearMethodGroup"
      :planetary-method-group="planetaryMethodGroup"
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
        <el-tag :type="statusType(result.status)" size="large">{{ statusText(result.status) }}</el-tag>
      </div>
      <div class="metric"><span class="label">健康度</span><strong>{{ result.health_score }}</strong></div>
      <div class="metric"><span class="label">故障概率</span><strong>{{ percent(result.fault_likelihood) }}</strong></div>
      <div class="metric"><span class="label">转频</span><strong>{{ result.rot_freq_hz ?? '-' }} Hz</strong></div>
      <div class="metric fault-label-metric"><span class="label">故障标签</span><strong class="fault-label-text">{{ result.fault_label || '-' }}</strong></div>
    </div>

    <!-- 单方法结果摘要 -->
    <div v-if="result && runMode === 'single'" class="summary-band">
      <div class="metric">
        <span class="label">方法</span>
        <el-tag :type="methodCategoryTag" size="large">{{ selectedMethodInfo?.label || selectedMethod }}</el-tag>
      </div>
      <div class="metric"><span class="label">转频</span><strong>{{ result.rot_freq_hz ?? '-' }} Hz</strong></div>
      <div class="metric" v-if="result.health_score"><span class="label">健康度</span><strong>{{ result.health_score }}</strong></div>
      <div class="metric" v-if="result.status"><span class="label">状态</span><el-tag :type="statusType(result.status)">{{ statusText(result.status) }}</el-tag></div>
    </div>

    <el-empty v-if="!result && !loading" :description="runMode === 'single' ? '请选择分析方法后运行' : '请点击运行开始诊断'" />

    <!-- ========== 单方法结果详情 ========== -->
    <SingleResultPanels
      v-if="result && runMode === 'single'"
      :result="result"
      :selected-method-info="selectedMethodInfo"
      :filter-planetary-result="filterPlanetaryResult"
    />

    <!-- ========== 全方法/集成诊断结果详情 ========== -->
    <EnsembleResultPanels
      v-if="result && runMode !== 'single'"
      :result="result"
      :has-all-results="hasAllResults"
      :bearing-vote-rows="bearingVoteRows"
      :gear-vote-rows="gearVoteRows"
      :best-indicator-rows="bestIndicatorRows"
      :ds-fault-prob-rows="dsFaultProbRows"
      :all-bearing-rows="allBearingRows"
      :all-gear-rows="allGearRows"
      :all-best-indicator-rows="allBestIndicatorRows"
    />
  </div>
</template>

<script setup>
import ResearchToolbar from '../components/research/ResearchToolbar.vue'
import SingleResultPanels from '../components/research/SingleResultPanels.vue'
import EnsembleResultPanels from '../components/research/EnsembleResultPanels.vue'
import { useResearchDiagnosis, percent, statusType, statusText } from '../composables/useResearchDiagnosis'

const {
  devices, selectedDeviceId, selectedBatchIndex, selectedChannel,
  runMode, selectedMethod, denoise, profile, loading, result,
  currentBatches, currentChannels, canRun,
  bearingMethodGroup, gearMethodGroup, planetaryMethodGroup,
  selectedMethodInfo, methodCategoryTag, filterPlanetaryResult,
  bearingVoteRows, gearVoteRows, bestIndicatorRows, dsFaultProbRows,
  hasAllResults, allBearingRows, allGearRows, allBestIndicatorRows,
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
