<template>
  <section class="composite-result">
    <el-alert title="研究组合：故障结论未知，结果不参与生产评分、融合投票或告警。" type="info" :closable="false" show-icon />
    <p>计算状态：{{ compositeCalculationState(result.analysis?.status) }}</p>
    <p v-if="result.analysis?.reason" class="reason">{{ compositeReason(result.analysis.reason) }}</p>
    <p v-if="result.analysis_method === 'composite_cvs_med_msb'" class="reason">CVS需要采集记录提供的真实相位与空间方位；缺失时不会用原始信号替代分离结果。</p>
    <el-table :data="compositeStages(result)" size="small" empty-text="缺少运行前提，尚未进入计算阶段">
      <el-table-column prop="name" label="阶段" />
      <el-table-column prop="state" label="计算状态" width="110" />
      <el-table-column prop="reason" label="条件或限制" />
    </el-table>
    <el-descriptions :column="2" border size="small" class="metrics">
      <el-descriptions-item v-for="item in compositeMetrics(result)" :key="item.name" :label="item.name">{{ item.value }}</el-descriptions-item>
      <el-descriptions-item v-if="data.decomposition" label="模态中心 Hz">{{ compositeValue(data.decomposition.center_frequencies_hz) }}</el-descriptions-item>
      <el-descriptions-item v-if="data.selection" label="选中分量">{{ compositeValue(data.selection.selected_indices) }}</el-descriptions-item>
      <el-descriptions-item v-if="data.ica" label="ICA计算状态">{{ compositeValue(data.ica.status) }} / 秩 {{ compositeValue(data.ica.numerical_rank) }}</el-descriptions-item>
      <el-descriptions-item v-if="data.cvs" label="CVS完整圈数">{{ compositeValue(data.cvs.cycles) }}</el-descriptions-item>
      <el-descriptions-item v-if="data.cvs" label="CVS相位覆盖">{{ compositeValue(data.cvs.coverage_fraction) }}</el-descriptions-item>
      <el-descriptions-item v-if="data.med" label="MED迭代">{{ compositeValue(data.med.iterations) }} / {{ data.med.converged ? '已收敛' : '未收敛' }}</el-descriptions-item>
    </el-descriptions>
    <div class="plots">
      <div v-for="curve in curves" :key="curve.title">
        <h4>{{ curve.title }} · {{ curve.amplitude_unit }}</h4>
        <VibrationChart :option="chartOption(curve)" :height="250" />
      </div>
    </div>
    <p class="reason">{{ compositeReason(result.evaluation?.reason) }} 真实数据效果尚未验证。</p>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import VibrationChart from '../charts/VibrationChart.vue'
import { compositeStages, compositeMetrics, compositeReason, compositeValue, compositeCurves, compositeCalculationState } from '../../utils/compositeResearch'
const props = defineProps({ result: { type: Object, required: true } })
const data = computed(() => props.result.analysis?.data || {})
const curves = computed(() => compositeCurves(props.result))
const chartOption = curve => ({
  tooltip: { trigger: 'axis' }, grid: { left: 55, right: 20, bottom: 40, top: 20 },
  xAxis: { type: 'value', name: curve.axis_unit }, yAxis: { type: 'value', scale: true },
  series: [{ type: 'line', showSymbol: false, connectNulls: false, data: curve.points }],
})
</script>
<style scoped>
.composite-result { min-width: 0; padding: 16px; border: 1px solid #e5e7eb; border-radius: 8px; background: white; }
.metrics { margin-top: 16px; }
.plots { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.reason { color: #64748b; line-height: 1.6; }
</style>
