<template>
  <div class="grid">
    <!-- D-S 证据融合面板 -->
    <section v-if="result.ensemble?.ds_fusion" class="panel">
      <div class="panel-title">
        <span>D-S 证据融合</span>
        <el-tag v-if="result.ensemble?.ds_fusion?.conflict_coefficient > 0.8" type="danger" effect="plain" size="small">高冲突</el-tag>
        <el-tag v-else type="success" effect="plain" size="small">低冲突</el-tag>
      </div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="主导故障">{{ result.ensemble?.ds_fusion?.dominant_fault || '-' }}</el-descriptions-item>
        <el-descriptions-item label="主导概率">{{ percent(result.ensemble?.ds_fusion?.dominant_probability) }}</el-descriptions-item>
        <el-descriptions-item label="不确定性(Θ)">{{ percent(result.ensemble?.ds_fusion?.uncertainty) }}</el-descriptions-item>
        <el-descriptions-item label="冲突系数">{{ fmt(result.ensemble?.ds_fusion?.conflict_coefficient) }}</el-descriptions-item>
      </el-descriptions>
    </section>

    <section v-if="result.ensemble" class="panel">
      <div class="panel-title">
        <span>集成证据</span>
        <el-tag effect="plain">{{ result.ensemble?.profile }}</el-tag>
      </div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="轴承置信度">{{ percent(result.ensemble?.bearing_confidence) }}</el-descriptions-item>
        <el-descriptions-item label="齿轮置信度">{{ percent(result.ensemble?.gear_confidence) }}</el-descriptions-item>
        <el-descriptions-item label="时域置信度">{{ percent(result.ensemble?.time_confidence) }}</el-descriptions-item>
        <el-descriptions-item label="轴承投票率">{{ percent(result.ensemble?.bearing_vote_fraction) }}</el-descriptions-item>
        <el-descriptions-item label="最佳轴承算法">{{ result.ensemble?.best_bearing || '-' }}</el-descriptions-item>
        <el-descriptions-item label="最佳齿轮算法">{{ result.ensemble?.best_gear || '-' }}</el-descriptions-item>
      </el-descriptions>
    </section>

    <section class="panel">
      <div class="panel-title">时域指标</div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="RMS">{{ fmt(result.time_features?.rms) }}</el-descriptions-item>
        <el-descriptions-item label="峭度">{{ fmt(result.time_features?.kurtosis) }}</el-descriptions-item>
        <el-descriptions-item label="峰值因子">{{ fmt(result.time_features?.crest_factor) }}</el-descriptions-item>
        <el-descriptions-item label="RMS MAD-Z">{{ fmt(result.time_features?.rms_mad_z) }}</el-descriptions-item>
        <el-descriptions-item label="CUSUM">{{ fmt(result.time_features?.cusum_score) }}</el-descriptions-item>
        <el-descriptions-item label="EWMA">{{ fmt(result.time_features?.ewma_drift) }}</el-descriptions-item>
      </el-descriptions>
    </section>

    <!-- D-S 融合故障概率分布表 -->
    <section v-if="result.ensemble?.ds_fusion?.fused_bpa" class="panel wide">
      <div class="panel-title">D-S 融合故障概率分布</div>
      <el-table :data="dsFaultProbRows" border size="small" max-height="300">
        <el-table-column prop="fault" label="故障类型" min-width="180" />
        <el-table-column prop="bpa" label="概率(BPA)" width="120">
          <template #default="{ row }">{{ percent(row.bpa) }}</template>
        </el-table-column>
        <el-table-column prop="belief" label="信念(Bel)" width="120">
          <template #default="{ row }">{{ percent(row.belief) }}</template>
        </el-table-column>
        <el-table-column prop="plausibility" label="似然(Pl)" width="120">
          <template #default="{ row }">{{ percent(row.plausibility) }}</template>
        </el-table-column>
      </el-table>
    </section>

    <section v-if="result.ensemble || hasAllResults" class="panel wide">
      <div class="panel-title">轴承算法投票</div>
      <!-- 集成诊断模式：投票数据 -->
      <el-table v-if="result.ensemble" :data="bearingVoteRows" border size="small" max-height="320">
        <el-table-column prop="method" label="算法" min-width="180" />
        <el-table-column prop="confidence" label="置信度" width="110">
          <template #default="{ row }">{{ percent(row.confidence) }}</template>
        </el-table-column>
        <el-table-column prop="param_hits" label="参数命中" width="100" />
        <el-table-column prop="stat_hits" label="统计命中" width="100" />
        <el-table-column prop="strongest_score" label="最强证据" width="100" />
        <el-table-column prop="hits" label="证据" min-width="220" />
      </el-table>
      <!-- 全部方法模式：各方法检出摘要 -->
      <el-table v-else :data="allBearingRows" border size="small" max-height="320">
        <el-table-column prop="method" label="诊断方法" width="160" />
        <el-table-column prop="faults" label="检出故障">
          <template #default="{ row }">
            <el-tag v-for="(f, idx) in row.faults" :key="idx" :type="((f.snr ?? f.score) > 5 || f.score === '?') ? 'danger' : 'warning'" size="small" style="margin-right:6px;margin-bottom:4px">
              {{ f.fault_type }} ({{ f.snr != null ? 'SNR' : 'score' }}={{ f.snr ?? f.score }})
            </el-tag>
            <el-text v-if="row.evaluationStatus !== 'evaluated' && !row._error" type="info" size="small">输入不足，暂不可判定</el-text>
            <el-text v-else-if="row.faults.length === 0 && !row._error" type="info" size="small">未检出显著故障</el-text>
            <el-text v-if="row._error" type="danger" size="small">{{ row.params }}</el-text>
          </template>
        </el-table-column>
        <el-table-column prop="params" label="关键参数" min-width="200">
          <template #default="{ row }">
            <el-text v-if="!row._error" type="info" size="small">{{ row.params }}</el-text>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section v-if="result.ensemble || hasAllResults" class="panel wide">
      <div class="panel-title">齿轮算法投票</div>
      <!-- 集成诊断模式：投票数据 -->
      <el-table v-if="result.ensemble" :data="gearVoteRows" border size="small" max-height="260">
        <el-table-column prop="method" label="算法" min-width="180" />
        <el-table-column prop="confidence" label="置信度" width="110">
          <template #default="{ row }">{{ percent(row.confidence) }}</template>
        </el-table-column>
        <el-table-column prop="critical_hits" label="严重命中" width="100" />
        <el-table-column prop="warning_hits" label="预警命中" width="100" />
        <el-table-column prop="hits" label="证据" min-width="220" />
      </el-table>
      <!-- 全部方法模式：各方法指标 -->
      <el-table v-else :data="allGearRows" border size="small" max-height="260">
        <el-table-column prop="method" label="诊断方法" width="140" />
        <el-table-column prop="ser" label="SER" width="100">
          <template #default="{ row }">
            <el-tag v-if="row._error" type="danger" size="small">{{ row._errMsg?.substring(0,20) }}</el-tag>
            <el-tag v-else-if="row.ser != null" :type="indicatorType(row.indicators?.ser)" size="small">{{ row.ser?.toFixed(3) }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="car" label="CAR" width="90">
          <template #default="{ row }">
            <span v-if="!row._error && row.car != null" :class="indicatorClass(row.indicators?.car)">{{ row.car?.toFixed(2) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="fm0" label="FM0" width="90">
          <template #default="{ row }">
            <span v-if="!row._error && row.fm0 != null" :class="indicatorClass(row.indicators?.fm0)">{{ row.fm0?.toFixed(2) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="fm4" label="FM4" width="90">
          <template #default="{ row }">
            <span v-if="!row._error && row.fm4 != null" :class="indicatorClass(row.indicators?.fm4)">{{ row.fm4?.toFixed(2) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="sideband_count" label="显著边频数" width="110" />
        <el-table-column prop="alerts" label="阈值告警">
          <template #default="{ row }">
            <el-tag v-for="(a, idx) in row.alerts" :key="idx" :type="a.level === 'critical' ? 'danger' : 'warning'" size="small" style="margin-right:6px;margin-bottom:4px">
              {{ a.indicator }}
            </el-tag>
            <el-text v-if="row.alerts.length === 0 && !row._error" type="info" size="small">无告警</el-text>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section v-if="result.ensemble || hasAllResults" class="panel wide">
      <div class="panel-title">最佳算法指标</div>
      <!-- 集成诊断模式 -->
      <el-table v-if="result.ensemble" :data="bestIndicatorRows" border size="small" max-height="320">
        <el-table-column prop="source" label="来源" width="90" />
        <el-table-column prop="name" label="指标" min-width="160" />
        <el-table-column prop="value" label="数值" min-width="140" />
        <el-table-column prop="state" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.type" size="small">{{ row.state }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <!-- 全部方法模式：所有方法故障指示器汇总 -->
      <el-table v-else :data="allBestIndicatorRows" border size="small" max-height="320">
        <el-table-column prop="source" label="方法" width="160" />
        <el-table-column prop="name" label="指标" min-width="160" />
        <el-table-column prop="value" label="数值" min-width="140" />
        <el-table-column prop="state" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.type" size="small">{{ row.state }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<script setup>
import { fmt, percent } from '../../composables/useResearchDiagnosis'

const indicatorType = (indicator) => indicator?.critical ? 'danger' : indicator?.warning ? 'warning' : 'success'
const indicatorClass = (indicator) => indicator?.critical ? 'text-danger' : indicator?.warning ? 'text-warning' : ''

defineProps({
  result: { type: Object, required: true },
  hasAllResults: { type: Object, default: null },
  bearingVoteRows: { type: Array, default: () => [] },
  gearVoteRows: { type: Array, default: () => [] },
  bestIndicatorRows: { type: Array, default: () => [] },
  dsFaultProbRows: { type: Array, default: () => [] },
  allBearingRows: { type: Array, default: () => [] },
  allGearRows: { type: Array, default: () => [] },
  allBestIndicatorRows: { type: Array, default: () => [] },
})
</script>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  min-width: 0;
}

.panel.wide { grid-column: 1 / -1; }

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  margin-bottom: 12px;
}

@media (max-width: 1100px) {
  .grid { grid-template-columns: 1fr; }
}
</style>
