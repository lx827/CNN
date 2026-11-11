<template>
  <div class="grid">
    <section v-for="evaluation in result.evaluations || []" :key="evaluation.object_id" class="panel">
      <div class="panel-title">{{ evaluation.object_id }} · 对象证据评估</div>
      <el-tag type="info">{{ evaluationStatusText(evaluation.evaluation_status) }}</el-tag>
      <span> · 对象结论 {{ evaluation.diagnosis_conclusion }}</span>
      <p v-if="evaluation.reason">{{ evaluation.reason }}</p>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="正常证据质量">{{ percent(evaluation.fusion?.normal_mass) }}</el-descriptions-item>
        <el-descriptions-item label="异常证据质量">{{ percent(evaluation.fusion?.anomaly_mass) }}</el-descriptions-item>
        <el-descriptions-item label="未知质量">{{ percent(evaluation.fusion?.ignorance_mass) }}</el-descriptions-item>
        <el-descriptions-item label="冲突">{{ fmt(evaluation.fusion?.conflict) }}</el-descriptions-item>
      </el-descriptions>
      <h4>依赖分组</h4>
      <p v-if="!evaluation.fusion?.groups?.length">没有可融合的有效证据。</p>
      <ul v-else>
        <li v-for="(group, index) in evaluation.fusion.groups" :key="index">{{ group.evidence_ids.join(' / ') }} · {{ group.dependencies.join(' / ') }}</li>
      </ul>
      <p class="hint">共享原始信号、分解或包络后端的证据按依赖关系分组，不按方法数量重复投票。</p>
    </section>

    <section class="panel">
      <div class="panel-title">时域原始指标</div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="RMS">{{ fmt(result.time_features?.rms) }}</el-descriptions-item>
        <el-descriptions-item label="峭度">{{ fmt(result.time_features?.kurtosis) }}</el-descriptions-item>
        <el-descriptions-item label="峰值因子">{{ fmt(result.time_features?.crest_factor) }}</el-descriptions-item>
        <el-descriptions-item label="RMS MAD-Z">{{ fmt(result.time_features?.rms_mad_z) }}</el-descriptions-item>
      </el-descriptions>
      <p class="hint">原始统计读数本身不构成额外独立投票。</p>
    </section>

    <section class="panel wide">
      <div class="panel-title">各方法对象结论</div>
      <p v-if="methodRows.length === 0">暂无方法评估结果。</p>
      <div v-for="row in methodRows" :key="row.key" class="method-row">
        <strong>{{ row.method }}</strong>
        <el-tag :type="row.view.tagType" size="small">{{ row.view.text }}</el-tag>
        <span>健康度 {{ row.view.scoreText }}</span>
        <span class="hint">{{ row.reason || '—' }}</span>
      </div>
    </section>

    <section v-for="(gear, key) in planetaryResults" :key="key" class="panel wide">
      <PlanetaryResult :result="gear" />
    </section>
    <section class="panel wide" v-if="result.recommendation">
      <div class="panel-title">诊断建议</div><p>{{ result.recommendation }}</p>
    </section>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import PlanetaryResult from './PlanetaryResult.vue'
import { fmt, percent, evaluationStatusText } from '../../utils/researchDisplay'
import { getDiagnosisView } from '../../utils/diagnosisStatus'
const props = defineProps({ result: { type: Object, required: true } })
const methodRows = computed(() => ['bearing_results', 'gear_results'].flatMap(kind =>
  Object.entries(props.result[kind] || {}).map(([method, local]) => ({
    key: `${kind}:${method}`, method, view: getDiagnosisView(local),
    reason: local?.reason || local?.error,
  }))))
const planetaryResults = computed(() => Object.fromEntries(Object.entries(props.result.gear_results || {}).filter(([, local]) => local?.is_planetary)))
</script>
<style scoped>
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.panel { background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; min-width: 0; }
.wide { grid-column: 1 / -1; }
.panel-title { font-weight: 600; margin-bottom: 12px; }
.hint { color: #64748b; line-height: 1.6; }
.method-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 12px 0; }
@media (max-width: 1100px) { .grid { grid-template-columns: 1fr; } }
</style>
