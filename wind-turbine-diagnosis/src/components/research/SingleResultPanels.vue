<template>
  <div class="result-grid">
    <!-- 轴承方法 -->
    <template v-if="selectedMethodInfo?.category === 'bearing'">
      <section class="panel">
        <div class="panel-title">方法分析结果</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="评估状态">
            <el-tag :type="evaluationStatusType(result.evaluation?.status)" size="small">
              {{ evaluationStatusText(result.evaluation?.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="result.algorithm" label="实际算法">{{ result.algorithm }}</el-descriptions-item>
          <el-descriptions-item v-if="result.reason || result.fallback_reason" label="适用条件">{{ bearingReasonText(result.reason || result.fallback_reason) }}</el-descriptions-item>
          <el-descriptions-item label="实际频带">
            <template v-if="result.band">
              {{ fmt(result.band.low_hz) }} ~ {{ fmt(result.band.high_hz) }} Hz
              （中心 {{ fmt(result.band.center_hz) }} Hz，带宽 {{ fmt(result.band.width_hz) }} Hz）
            </template>
            <template v-else>-</template>
          </el-descriptions-item>
          <el-descriptions-item v-for="(value, name) in result.features" :key="name" :label="name">
            {{ fmt(value) }}
          </el-descriptions-item>
        </el-descriptions>
      </section>
      <section v-if="result.evaluation_kind !== 'sc_scoh'" class="panel">
        <div class="panel-title">轴承包络评估指标</div>
        <el-empty v-if="bearingEvaluationItems.length === 0" description="暂无可评估的包络指标" :image-size="60" />
        <el-descriptions v-else :column="2" border size="small">
          <el-descriptions-item v-for="entry in bearingEvaluationItems" :key="entry.key" :label="entry.name">
            <template v-if="entry.info && typeof entry.info === 'object'">
              <el-tag :type="entry.info.critical || entry.info.significant ? 'danger' : entry.info.warning ? 'warning' : 'success'" size="small">
                {{ entry.info.critical ? '严重' : entry.info.significant ? '命中' : entry.info.warning ? '预警' : '正常' }}
              </el-tag>
              <span v-if="entry.info.snr != null" style="margin-left:4px">SNR={{ fmt(entry.info.snr) }}</span>
              <span v-if="entry.info.value != null" style="margin-left:4px">值={{ fmt(entry.info.value) }}</span>
              <span v-if="entry.info.detected_hz != null" style="margin-left:4px">检出={{ fmt(entry.info.detected_hz) }}Hz</span>
            </template>
            <template v-else>{{ fmt(entry.info) }}</template>
          </el-descriptions-item>
        </el-descriptions>
      </section>
      <section v-if="scScohItems.length" class="panel wide">
        <div class="panel-title">SC/SCoh 专属指标</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item v-for="entry in scScohItems" :key="entry.key" :label="entry.name">
            <el-tag :type="entry.info.evaluable === false ? 'info' : entry.info.significant ? 'warning' : 'success'" size="small">
              {{ entry.info.evaluable === false ? '不可评估' : entry.info.significant ? '显著' : '未显著' }}
            </el-tag>
            <span style="margin-left:4px">理论循环频率={{ fmt(entry.info.theory_cyclic_frequency_hz ?? entry.info.theory_hz) }}Hz</span>
            <span v-if="entry.info.detected_cyclic_frequency_hz != null" style="margin-left:4px">检出={{ fmt(entry.info.detected_cyclic_frequency_hz) }}Hz</span>
            <span v-if="entry.info.carrier_frequency_hz != null" style="margin-left:4px">载频={{ fmt(entry.info.carrier_frequency_hz) }}Hz</span>
            <span style="margin-left:4px">SCoh={{ fmt(entry.info.scoh_peak) }}</span>
            <span style="margin-left:4px">相干峰背景比={{ fmt(entry.info.coherence_background_ratio) }}</span>
            <span style="margin-left:4px">复相关峰背景比={{ fmt(entry.info.sc_background_ratio) }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </section>
    </template>

    <PlanetaryResult v-if="result.is_planetary" class="panel wide" :result="result" />

    <!-- 齿轮方法 -->
    <template v-if="selectedMethodInfo?.category === 'gear' && !result.is_planetary">
      <section class="panel">
        <div class="panel-title">齿轮指标</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="SER">{{ fmt(result.ser) }}</el-descriptions-item>
          <el-descriptions-item label="CAR">{{ fmt(result.car) }}</el-descriptions-item>
          <el-descriptions-item v-if="result.fm0" label="FM0">{{ fmt(result.fm0) }}</el-descriptions-item>
          <el-descriptions-item v-if="result.fm4" label="FM4">{{ fmt(result.fm4) }}</el-descriptions-item>
          <el-descriptions-item v-if="result.m6a" label="M6A">{{ fmt(result.m6a) }}</el-descriptions-item>
          <el-descriptions-item v-if="result.m8a" label="M8A">{{ fmt(result.m8a) }}</el-descriptions-item>
          <el-descriptions-item v-if="result.mesh_freq_hz" label="啮合频率">{{ fmt(result.mesh_freq_hz) }} Hz</el-descriptions-item>
          <el-descriptions-item v-if="result.mesh_order" label="啮合阶次">{{ fmt(result.mesh_order) }}</el-descriptions-item>
        </el-descriptions>
      </section>
      <section class="panel">
        <div class="panel-title">齿轮故障指示器</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item v-for="(val, name) in result.fault_indicators" :key="name" :label="name">
            <template v-if="val && typeof val === 'object'">
              <el-tag :type="val.critical ? 'danger' : val.warning ? 'warning' : 'success'" size="small">{{ val.critical ? '严重' : val.warning ? '预警' : '正常' }}</el-tag>
              <span v-if="val.value" style="margin-left:4px">值={{ fmt(val.value) }}</span>
            </template>
            <template v-else>{{ fmt(val) }}</template>
          </el-descriptions-item>
        </el-descriptions>
      </section>
    </template>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import PlanetaryResult from './PlanetaryResult.vue'
import { fmt, evaluationStatusType, evaluationStatusText } from '../../composables/useResearchDiagnosis'
import { bearingEvaluationEntries, scScohEntries, bearingReasonText } from '../../utils/bearingDiagnosis'
const props = defineProps({
  result: { type: Object, required: true },
  selectedMethodInfo: { type: Object, default: null },
})
const bearingEvaluationItems = computed(() => bearingEvaluationEntries(props.result))
const scScohItems = computed(() => scScohEntries(props.result))
</script>

<style scoped>
.result-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; min-width: 0; }
.panel.wide { grid-column: 1 / -1; }
.panel-title { display: flex; align-items: center; justify-content: space-between; font-weight: 600; margin-bottom: 12px; }
@media (max-width: 1100px) { .result-grid { grid-template-columns: 1fr; } }
</style>
