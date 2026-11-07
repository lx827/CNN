<template>
  <div class="data-view">
    <!-- 标题栏 -->
    <el-card class="header-card">
      <div class="header-bar">
        <span class="title">振动数据查看</span>
        <div class="actions">
          <el-button type="danger" size="small" @click="onDeleteAllSpecial" :loading="deleteLoading">
            <el-icon><Delete /></el-icon> 清空所有特殊数据
          </el-button>
          <el-button type="primary" size="small" @click="loadAllDevices" :loading="loading">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 设备批次表格 -->
    <DeviceTable
      :data="deviceTableData"
      :loading="loading"
      :selected-device-id="selectedDevice?.device_id"
      :selected-batch-index="selectedBatch?.batch_index"
      @select-batch="selectBatch"
      @refresh="loadAllDevices"
      @batch-deleted="onBatchDeleted"
    />

    <!-- 选中批次详情 -->
    <el-card v-if="selectedDevice && selectedBatch" class="detail-card">
      <template #header>
        <DetailHeader
          :device="selectedDevice"
          :batch="selectedBatch"
          v-model:channel="selectedChannel"
          :channel-options="channelOptions"
          v-model:maxFreq="maxFreq"
          v-model:denoiseMethod="denoiseMethod"
          v-model:enableDetrend="enableDetrend"
          :reanalyzing="reanalyzing"
          :reanalyzingAll="reanalyzingAll"
          @export-csv="onExportCSV"
          @reanalyze="onReanalyze"
          @reanalyze-all="onReanalyzeAll"
          @delete-batch="onDeleteBatch(selectedDevice.device_id, selectedBatch.batch_index)"
          @goto-research="gotoResearchDiagnosis"
        />
      </template>

      <DiagnosisAlert :status="selectedBatch.diagnosis_status" :description="diagnosisDesc" />

      <!-- 时域波形：始终自动加载 -->
      <TimeDomainPanel :chart-option="timeOption" />

      <!-- 统计指标 -->
      <StatsSection
        v-model:stats-window-size="statsWindowSize"
        v-model:stats-step="statsStep"
        :computed-stats="computedStats"
        :loading-stats="loadingStats"
        :stats-data="statsData"
        :windowed-option="windowedOption"
        @compute="computeStats"
        @clear="clearStats"
      />

      <!-- FFT 频谱 / 包络谱 -->
      <FftEnvelopeSection
        v-model:envelope-method="envelopeMethod"
        :computed-f-f-t="computedFFT"
        :loading-f-f-t="loadingFFT"
        :fft-option="fftOption"
        :computed-envelope="computedEnvelope"
        :loading-envelope="loadingEnvelope"
        :envelope-data="envelopeData"
        :envelope-option="envelopeOption"
        :envelope-method-label="envelopeMethodLabel"
        @compute-fft="computeFFT"
        @clear-fft="clearFFT"
        @compute-envelope="computeEnvelope"
        @clear-envelope="clearEnvelope"
      />

      <!-- 齿轮诊断 -->
      <GearSection
        v-model:gear-method="gearMethod"
        :computed-gear="computedGear"
        :loading-gear="loadingGear"
        :gear-data="gearData"
        :gear-method-label="gearMethodLabel"
        @compute="computeGear"
        @clear="clearGear"
      />

      <!-- 综合故障诊断 -->
      <ComprehensiveSection
        v-model:analyze-strategy="analyzeStrategy"
        v-model:analyze-denoise="analyzeDenoise"
        v-model:full-analysis-denoise="fullAnalysisDenoise"
        :computed-strategy-analyze="computedStrategyAnalyze"
        :loading-strategy-analyze="loadingStrategyAnalyze"
        :strategy-analyze-data="strategyAnalyzeData"
        :analyze-strategy-label="analyzeStrategyLabel"
        :computed-full-analysis="computedFullAnalysis"
        :loading-full-analysis="loadingFullAnalysis"
        :full-analysis-data="fullAnalysisData"
        :bearing-summary-table="bearingSummaryTable"
        :gear-summary-table="gearSummaryTable"
        :fault-freq-annotations="faultFreqAnnotations"
        @compute-strategy="computeStrategyAnalyze"
        @clear-strategy="clearStrategyAnalyze"
        @compute-full="computeFullAnalysis"
        @clear-full="clearFullAnalysis"
        @goto-research="gotoResearchDiagnosis"
      />

      <!-- 阶次追踪 -->
      <OrderSection
        v-model:order-freq-min="orderFreqMin"
        v-model:order-freq-max="orderFreqMax"
        v-model:order-samples-per-rev="orderSamplesPerRev"
        :computed-order="computedOrder"
        :loading-order="loadingOrder"
        :order-data="orderData"
        :order-option="orderOption"
        @compute="computeOrder"
        @clear="clearOrder"
      />

      <!-- 倒谱分析 -->
      <CepstrumSection
        v-model:cepstrum-max-quefrency="cepstrumMaxQuefrency"
        :computed-cepstrum="computedCepstrum"
        :loading-cepstrum="loadingCepstrum"
        :cepstrum-data="cepstrumData"
        :cepstrum-option="cepstrumOption"
        @compute="computeCepstrum"
        @clear="clearCepstrum"
      />

      <!-- STFT 时频谱 -->
      <StftSection
        v-model:stft-nperseg="stftNperseg"
        v-model:stft-noverlap="stftNoverlap"
        :computed-s-t-f-t="computedSTFT"
        :loading-s-t-f-t="loadingSTFT"
        :stft-option="stftOption"
        @compute="computeSTFT"
        @clear="clearSTFT"
      />

      <!-- 阶次/包络诊断明细 -->
      <DiagnosisDetailSection
        :show-detail="showDiagnosisDetail"
        :loading-detail="loadingDiagnosisDetail"
        :batch="selectedBatch"
        :order-data="orderData"
        @load="loadDiagnosisDetail"
        @hide="showDiagnosisDetail = false"
      />
    </el-card>

    <el-empty v-else description="点击上方表格中的批次时间，查看详细数据" />


  </div>
</template>

<script setup>
import DeviceTable from '../components/dataview/DeviceTable.vue'
import DetailHeader from '../components/dataview/DetailHeader.vue'
import DiagnosisAlert from '../components/dataview/DiagnosisAlert.vue'
import TimeDomainPanel from '../components/dataview/TimeDomainPanel.vue'
import StatsSection from '../components/dataview/StatsSection.vue'
import FftEnvelopeSection from '../components/dataview/FftEnvelopeSection.vue'
import GearSection from '../components/dataview/GearSection.vue'
import ComprehensiveSection from '../components/dataview/ComprehensiveSection.vue'
import OrderSection from '../components/dataview/OrderSection.vue'
import CepstrumSection from '../components/dataview/CepstrumSection.vue'
import StftSection from '../components/dataview/StftSection.vue'
import DiagnosisDetailSection from '../components/dataview/DiagnosisDetailSection.vue'
import { useDataView } from '../composables/useDataView'

const {
  loading, deleteLoading, reanalyzing, reanalyzingAll, deviceTableData,
  selectedDevice, selectedBatch, selectedChannel, maxFreq, channelOptions, enableDetrend,
  envelopeMethod, envelopeMethodLabel, gearMethod, gearMethodLabel, denoiseMethod,
  timeOption, fftOption, stftOption, envelopeOption, windowedOption, orderOption, cepstrumOption,
  computedFFT, computedSTFT, computedEnvelope, computedStats, computedOrder, computedCepstrum, computedGear,
  loadingFFT, loadingSTFT, loadingEnvelope, loadingStats, loadingOrder, loadingCepstrum, loadingGear,
  statsData, orderData, cepstrumData, gearData, envelopeData,
  computedFullAnalysis, loadingFullAnalysis, fullAnalysisData, fullAnalysisDenoise,
  computedStrategyAnalyze, loadingStrategyAnalyze, strategyAnalyzeData, analyzeStrategy, analyzeDenoise, analyzeStrategyLabel,
  showDiagnosisDetail, loadingDiagnosisDetail, faultFreqAnnotations,
  statsWindowSize, statsStep, stftNperseg, stftNoverlap,
  orderFreqMin, orderFreqMax, orderSamplesPerRev, cepstrumMaxQuefrency,
  bearingSummaryTable, gearSummaryTable, diagnosisDesc,
  onBatchDeleted, loadAllDevices, loadDiagnosisDetail, selectBatch,
  computeFFT, clearFFT, computeSTFT, clearSTFT, computeEnvelope, clearEnvelope,
  computeOrder, clearOrder, computeCepstrum, clearCepstrum, computeGear, clearGear,
  computeFullAnalysis, clearFullAnalysis, computeStrategyAnalyze, clearStrategyAnalyze,
  computeStats, clearStats, onExportCSV, onReanalyze, onReanalyzeAll,
  onDeleteBatch, onDeleteAllSpecial, gotoResearchDiagnosis,
} = useDataView()
</script>

<style scoped>
.data-view {
  padding: 0;
}

.header-card {
  margin-bottom: 16px;
}

.header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-size: 18px;
  font-weight: 600;
}

.actions {
  display: flex;
  gap: 8px;
}

.detail-card {
  margin-bottom: 20px;
}
</style>
