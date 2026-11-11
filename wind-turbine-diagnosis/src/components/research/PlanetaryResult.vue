<template>
  <section class="planetary-result">
    <el-alert :title="diagnosisView.text" :type="diagnosisView.alertType" :closable="false" show-icon :description="planetaryReasonText(result.reason)" />
    <el-descriptions :column="2" border size="small" class="details">
      <el-descriptions-item label="分析参考轴">{{ planetaryAxisText(result.mechanical_model?.reference_axis) }}</el-descriptions-item>
      <el-descriptions-item label="固定构件">{{ result.mechanical_model ? '齿圈' : '未配置' }}</el-descriptions-item>
      <el-descriptions-item label="啮合阶次">{{ number(result.mesh_order) }}</el-descriptions-item>
      <el-descriptions-item label="行星架阶次">{{ number(result.mechanical_model?.carrier_order) }}</el-descriptions-item>
      <el-descriptions-item label="行星轮相对行星架阶次">{{ number(result.mechanical_model?.planet_relative_to_carrier_order) }}</el-descriptions-item>
      <el-descriptions-item label="TSA 同步轴 / 完整转数">{{ result.tsa ? `${planetaryAxisText(result.tsa.reference_axis)} / ${result.tsa.revolutions}` : '未生成' }}</el-descriptions-item>
    </el-descriptions>
    <el-table :data="planetaryMetricRows(result)" border size="small" class="details">
      <el-table-column prop="name" label="原始指标" />
      <el-table-column label="值"><template #default="{ row }">{{ number(row.value) }}</template></el-table-column>
      <el-table-column label="计算状态 / 前提"><template #default="{ row }">{{ row.status === 'evaluated' ? '已计算，告警需可比基线' : planetaryReasonText(row.reason) }}</template></el-table-column>
    </el-table>
    <el-collapse class="details">
      <el-collapse-item v-for="(method, key) in result.planetary_methods" :key="key" :name="key" :title="`${methodNames[key] || key} · ${planetaryAxisText(method.reference_axis)} · ${method.status === 'computed' ? '已计算' : '不可评估'}`">
        <p v-if="method.reason">{{ planetaryReasonText(method.reason) }}</p>
        <p v-if="key === 'tsa_residual'">同架同步事件保留在 TSA 中，并从非同步残差中抑制；残差无峰不能排除同步损伤。</p>
        <el-table :data="method.peaks || []" border size="small">
          <el-table-column label="运动学候选"><template #default="{ row }">{{ planetaryCandidateText(row.name) }}</template></el-table-column>
          <el-table-column label="理论 / 峰阶次"><template #default="{ row }">{{ number(row.target_order) }} / {{ number(row.peak_order) }}</template></el-table-column>
          <el-table-column label="幅值背景比"><template #default="{ row }">{{ number(row.amplitude_to_background) }}</template></el-table-column>
          <el-table-column label="状态"><template #default="{ row }">{{ row.status === 'computed' ? '仅为候选证据' : planetaryReasonText(row.reason) }}</template></el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>
    <el-text type="info" size="small">健康行星排也有边带；候选峰和统计矩不能单独命名断齿、裂纹或磨损。真实数据效果尚未验证。</el-text>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { getDiagnosisView } from '../../utils/diagnosisStatus'
import { planetaryAxisText, planetaryCandidateText, planetaryMetricRows, planetaryReasonText } from '../../utils/planetaryDiagnosis'
const props = defineProps({ result: { type: Object, required: true } })
const diagnosisView = computed(() => getDiagnosisView(props.result))
const number = value => value == null || !Number.isFinite(Number(value)) ? '-' : Number(value).toFixed(4)
const methodNames = { narrowband: '啮合带包络', fullband: '全带包络', highpass: '高通包络', tsa_residual: 'TSA 非同步残差包络' }
</script>

<style scoped>
.planetary-result { min-width: 0; }
.details { margin: 12px 0; }
</style>
