<template>
  <el-row :gutter="16" class="spectrum-row">
    <el-col :span="24">
      <div class="section-header">
        <span class="chart-title">综合故障诊断</span>
        <div style="display: flex; align-items: center; gap: 8px;">
          <!-- 对象快速诊断 -->
          <template v-if="!computedStrategyAnalyze && !computedFullAnalysis">
            <el-select v-model="analyzeDenoise" size="small" style="width: 150px">
              <el-option label="无预处理" value="none" />
              <el-option label="小波去噪" value="wavelet" />
              <el-option label="VMD分解" value="vmd" />
              <el-option label="小波+VMD级联" value="wavelet_vmd" />
              <el-option label="小波+LMS级联" value="wavelet_lms" />
              <el-option label="EMD降噪" value="emd" />
              <el-option label="CEEMDAN降噪" value="ceemdan" />
              <el-option label="WP降噪" value="wavelet_packet" />
              <el-option label="CEEMDAN+WP降噪" value="ceemdan_wp" />
              <el-option label="EEMD降噪" value="eemd" />
              <el-option label="S-G平滑" value="savgol" />
            </el-select>
            <el-button
              type="success"
              size="small"
              :loading="loadingStrategyAnalyze"
              @click="$emit('compute-strategy')"
            >
              <el-icon><DataAnalysis /></el-icon> 对象诊断
            </el-button>
            <el-divider direction="vertical" />
          </template>
          <el-button v-if="computedStrategyAnalyze && !computedFullAnalysis" type="info" size="small" @click="$emit('clear-strategy')">
            <el-icon><Close /></el-icon> 收起诊断
          </el-button>
          <!-- 全算法诊断 -->
          <template v-if="!computedFullAnalysis">
            <el-select v-model="fullAnalysisDenoise" size="small" style="width: 150px">
              <el-option label="无预处理" value="none" />
              <el-option label="小波去噪" value="wavelet" />
              <el-option label="VMD分解" value="vmd" />
              <el-option label="小波+VMD级联" value="wavelet_vmd" />
              <el-option label="小波+LMS级联" value="wavelet_lms" />
              <el-option label="EMD降噪" value="emd" />
              <el-option label="CEEMDAN降噪" value="ceemdan" />
              <el-option label="WP降噪" value="wavelet_packet" />
              <el-option label="CEEMDAN+WP降噪" value="ceemdan_wp" />
              <el-option label="EEMD降噪" value="eemd" />
              <el-option label="S-G平滑" value="savgol" />
            </el-select>
            <el-button
              type="primary"
              size="small"
              :loading="loadingFullAnalysis"
              @click="$emit('compute-full')"
            >
              <el-icon><DataAnalysis /></el-icon> 全算法诊断
            </el-button>
          </template>
          <el-button v-else type="info" size="small" @click="$emit('clear-full')">
            <el-icon><Close /></el-icon> 收起
          </el-button>
        </div>
      </div>
      <div v-if="computedStrategyAnalyze && strategyAnalyzeData && !computedFullAnalysis">
        <!-- 对象诊断简洁结果 -->
        <el-alert
          :title="`对象诊断：${strategyStatusView.label}`"
          :type="strategyStatusView.alertType"
          :description="strategyAnalyzeData.recommendation || strategyAnalyzeData.reason"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        />
        <el-descriptions :column="4" size="small" border>
          <el-descriptions-item label="健康度">{{ strategyStatusView.scoreText }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ strategyStatusView.label }}</el-descriptions-item>
          <el-descriptions-item label="转频">{{ strategyAnalyzeData.rot_freq_hz }} Hz</el-descriptions-item>
          <el-descriptions-item label="峭度" v-if="strategyAnalyzeData.time_features">{{ strategyAnalyzeData.time_features.kurtosis?.toFixed(4) }}</el-descriptions-item>
          <el-descriptions-item label="RMS" v-if="strategyAnalyzeData.time_features">{{ strategyAnalyzeData.time_features.rms?.toFixed(4) }}</el-descriptions-item>
          <el-descriptions-item label="峰值因子" v-if="strategyAnalyzeData.time_features">{{ strategyAnalyzeData.time_features.crest_factor?.toFixed(4) }}</el-descriptions-item>
        </el-descriptions>
        <DiagnosisCoverage :result="strategyAnalyzeData" />
      </div>
      <div v-else-if="loadingStrategyAnalyze" class="placeholder">
        <el-icon class="is-loading"><Loading /></el-icon> 正在执行对象诊断...
      </div>
      <div v-if="computedFullAnalysis && fullAnalysisData">
        <!-- 综合结论 -->
        <el-alert
          :title="`综合诊断：${fullAnalysisStatusView.label}`"
          :type="fullAnalysisStatusView.alertType"
          :description="fullAnalysisData.recommendation || fullAnalysisData.reason"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        />

        <el-text :type="fullAnalysisStatusView.tone">健康度：{{ fullAnalysisStatusView.scoreText }}</el-text>
        <DiagnosisCoverage :result="fullAnalysisData" />
        <!-- 时域特征 -->
        <el-card size="small" style="margin-bottom: 12px">
          <template #header>
            <span style="font-weight: 600;">📊 时域特征参数</span>
            <el-text v-if="fullAnalysisData.rot_freq_hz" type="info" size="small" style="margin-left: 12px;">
              估计转频: {{ fullAnalysisData.rot_freq_hz }} Hz / {{ (fullAnalysisData.rot_freq_hz * 60).toFixed(0) }} RPM
            </el-text>
          </template>
          <el-descriptions :column="4" size="small" border v-if="fullAnalysisData.time_features">
            <el-descriptions-item label="峰值">{{ fullAnalysisData.time_features.peak?.toFixed(4) }}</el-descriptions-item>
            <el-descriptions-item label="RMS">{{ fullAnalysisData.time_features.rms?.toFixed(4) }}</el-descriptions-item>
            <el-descriptions-item label="峭度">{{ fullAnalysisData.time_features.kurtosis?.toFixed(4) }}</el-descriptions-item>
            <el-descriptions-item label="偏度">{{ fullAnalysisData.time_features.skewness?.toFixed(4) }}</el-descriptions-item>
            <el-descriptions-item label="裕度">{{ fullAnalysisData.time_features.margin?.toFixed(4) }}</el-descriptions-item>
            <el-descriptions-item label="峰值因子">{{ fullAnalysisData.time_features.crest_factor?.toFixed(4) }}</el-descriptions-item>
            <el-descriptions-item label="波形因子">{{ fullAnalysisData.time_features.shape_factor?.toFixed(4) }}</el-descriptions-item>
            <el-descriptions-item label="脉冲因子">{{ fullAnalysisData.time_features.impulse_factor?.toFixed(4) }}</el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- 轴承诊断各方法结果 -->
        <el-card size="small" style="margin-bottom: 12px">
          <template #header>
            <span style="font-weight: 600;">🔧 轴承诊断 — 各方法检出结论</span>
          </template>
          <el-table :data="bearingSummaryTable" size="small" border style="width: 100%">
            <template #empty>
              <el-text type="info" size="small">
                未配置轴承参数，请在<el-link type="primary" @click="$router.push('/devices')">设备配置</el-link>中设置轴承几何参数（n/d/D/α）
              </el-text>
            </template>
            <el-table-column prop="method" label="诊断方法" width="160" />
            <el-table-column prop="faults" label="检出故障">
              <template #default="{ row }">
                <el-tag v-for="(f, idx) in row.faults" :key="idx" :type="(f.snr ?? f.score) > 5 ? 'danger' : 'warning'" size="small" style="margin-right: 6px; margin-bottom: 4px;">
                  {{ f.fault_type }} ({{ f.snr != null ? 'SNR' : 'score' }}={{ f.snr ?? f.score }})
                </el-tag>
                <el-text type="info" size="small">评估条件：{{ row.evaluationStatus || 'unknown' }}</el-text>
                <el-text v-if="row.evaluationStatus === 'evaluated' && row.faults.length === 0" type="info" size="small">未检出显著故障</el-text>
              </template>
            </el-table-column>
            <el-table-column prop="params" label="关键参数" min-width="200">
              <template #default="{ row }">
                <el-text type="info" size="small">{{ row.params }}</el-text>
              </template>
            </el-table-column>
          </el-table>

          <!-- 各方法详细故障指示器 -->
          <el-collapse style="margin-top: 12px;">
            <el-collapse-item title="查看各方法详细指标" name="1">
              <div v-for="(bresult, methodKey) in fullAnalysisData.bearing_results" :key="methodKey" style="margin-bottom: 12px;">
                <el-text type="primary" size="small" style="font-weight: 600;">{{ bearingMethodLabel(methodKey) }}</el-text>
                <el-descriptions :column="3" size="small" border v-if="bearingEntries(bresult).length">
                  <el-descriptions-item
                    v-for="entry in bearingEntries(bresult)"
                    :key="entry.key"
                    :label="entry.source === 'sc_scoh' ? `SC/SCoh ${entry.name}` : entry.name"
                  >
                    <span v-if="entry.info.significant || entry.info.critical" style="color: #F5222D; font-weight: 600;">
                      检出 ({{ entry.info.detected_hz ?? entry.info.theory_hz }}Hz,
                      {{ entry.source === 'sc_scoh' ? `SCoh=${entry.info.scoh_peak}, 相干峰背景比=${entry.info.coherence_background_ratio}` : `SNR=${entry.info.snr}` }})
                    </span>
                    <span v-else-if="entry.info.evaluable === false || entry.info.significant == null" style="color: #999;">
                      不可评估（{{ entry.info.reason || '输入或频率覆盖不足' }}）
                    </span>
                    <span v-else style="color: #999;">
                      未检出 (理论{{ entry.info.theory_hz }}Hz)
                    </span>
                  </el-descriptions-item>
                </el-descriptions>
                <el-text v-else type="info" size="small">暂无可评估指标</el-text>
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-card>

        <!-- 齿轮诊断各方法结果 -->
        <el-card size="small" style="margin-bottom: 12px">
          <template #header>
            <span style="font-weight: 600;">⚙️ 齿轮诊断 — 各方法详细参数</span>
          </template>
          <PlanetaryResult v-for="(result, key) in planetaryResults" :key="key" :result="result" />
          <el-table v-if="!Object.keys(planetaryResults).length" :data="gearSummaryTable" size="small" border style="width: 100%">
            <template #empty>
              <el-text type="info" size="small">
                未配置齿轮参数，请在<el-link type="primary" @click="$router.push('/devices')">设备配置</el-link>中设置齿数（input/output）
              </el-text>
            </template>
            <el-table-column prop="method" label="诊断方法" width="140" />
            <el-table-column prop="ser" label="SER" width="100">
              <template #default="{ row }">
                <el-tag :type="row.ser > 3 ? 'danger' : row.ser > 1.5 ? 'warning' : 'success'" size="small">{{ row.ser?.toFixed(3) ?? '-' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="fm0" label="FM0" width="90">
              <template #default="{ row }">
                <span :class="row.fm0 > 10 ? 'text-danger' : row.fm0 > 5 ? 'text-warning' : ''">{{ row.fm0?.toFixed(2) ?? '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="fm4" label="FM4" width="90">
              <template #default="{ row }">
                <span :class="row.fm4 > 10 ? 'text-danger' : row.fm4 > 5 ? 'text-warning' : ''">{{ row.fm4?.toFixed(2) ?? '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="car" label="CAR" width="90">
              <template #default="{ row }">
                <span :class="row.car > 2 ? 'text-danger' : row.car > 1.2 ? 'text-warning' : ''">{{ row.car?.toFixed(2) ?? '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="sideband_count" label="显著边频数" width="110" />
            <el-table-column prop="alerts" label="阈值告警">
              <template #default="{ row }">
                <el-tag v-for="(a, idx) in row.alerts" :key="idx" :type="a.level === 'critical' ? 'danger' : 'warning'" size="small" style="margin-right: 6px; margin-bottom: 4px;">
                  {{ a.indicator }}
                </el-tag>
                <el-text v-if="row.alerts.length === 0" type="info" size="small">无告警</el-text>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
      <div v-else-if="loadingFullAnalysis" class="placeholder">
        <el-skeleton :rows="4" animated />
      </div>
      <div v-else class="placeholder">
        <el-empty description="点击按钮运行全算法故障诊断对比分析" :image-size="80" />
        <div v-if="faultFreqAnnotations" style="margin-top: 8px; text-align: center;">
          <el-text type="success" size="small">
            💡 已有诊断缓存，特征频率已标注在频谱图上
          </el-text>
          <el-link type="primary" size="small" style="margin-left: 8px;" @click="$emit('goto-research')">
            查看高级诊断详情 →
          </el-link>
        </div>
      </div>
    </el-col>
  </el-row>
</template>

<script setup>
import { computed } from 'vue'
import PlanetaryResult from '../research/PlanetaryResult.vue'
import { bearingMethodLabel } from '../../composables/useDataView'
import { bearingIndicatorEntries as bearingEntries } from '../../utils/bearingDiagnosis'
import DiagnosisCoverage from '../DiagnosisCoverage.vue'
import { getDiagnosisView } from '../../utils/diagnosisStatus'

const props = defineProps({
  computedStrategyAnalyze: { type: Boolean, default: false },
  loadingStrategyAnalyze: { type: Boolean, default: false },
  strategyAnalyzeData: { type: Object, default: null },
  computedFullAnalysis: { type: Boolean, default: false },
  loadingFullAnalysis: { type: Boolean, default: false },
  fullAnalysisData: { type: Object, default: null },
  bearingSummaryTable: { type: Array, default: () => [] },
  gearSummaryTable: { type: Array, default: () => [] },
  faultFreqAnnotations: { type: Object, default: null },
})

const analyzeDenoise = defineModel('analyzeDenoise', { type: String, default: 'none' })
const fullAnalysisDenoise = defineModel('fullAnalysisDenoise', { type: String, default: 'none' })

defineEmits(['compute-strategy', 'clear-strategy', 'compute-full', 'clear-full', 'goto-research'])

const strategyStatusView = computed(() => getDiagnosisView(props.strategyAnalyzeData))
const fullAnalysisStatusView = computed(() => getDiagnosisView(props.fullAnalysisData))
const planetaryResults = computed(() => Object.fromEntries(Object.entries(props.fullAnalysisData?.gear_results || {}).filter(([, result]) => result?.is_planetary)))
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
