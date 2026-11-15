<template>
  <el-row :gutter="16">
    <el-col :span="24">
      <div class="chart-title">时域波形</div>
      <VibrationChart :option="chartOption" />
    </el-col>
  </el-row>
</template>

<script setup>
import VibrationChart from '../charts/VibrationChart.vue'

defineProps({
  chartOption: { type: Object, default: null },
})
</script>
