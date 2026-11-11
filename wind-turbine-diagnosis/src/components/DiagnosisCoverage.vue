<template>
  <div class="diagnosis-coverage">
    <el-text v-if="result?.coverage === 'partial'" type="info">部分对象形成有效评估，综合结论仅覆盖有效证据。</el-text>
    <el-text v-if="result?.reason" type="info">{{ result.reason }}</el-text>
    <div v-for="(evaluation, index) in result?.evaluations || []" :key="`${evaluation.object_id}-${index}`">
      <span>{{ evaluation.object_id }}：</span>
      <el-tag :type="getDiagnosisView(evaluation).tagType" size="small">{{ getDiagnosisView(evaluation).label }}</el-tag>
      <el-text v-if="evaluation.reason" type="info"> {{ evaluation.reason }}</el-text>
    </div>
  </div>
</template>

<script setup>
import { getDiagnosisView } from '../utils/diagnosisStatus'
defineProps({ result: { type: Object, default: null } })
</script>

<style scoped>
.diagnosis-coverage { display: grid; gap: 6px; margin-top: 8px; }
</style>
