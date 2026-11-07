<template>
  <div class="result-grid">
    <!-- 轴承方法 -->
    <template v-if="selectedMethodInfo?.category === 'bearing'">
      <section class="panel">
        <div class="panel-title">包络域特征</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="包络峰值SNR">{{ fmt(result.features?.envelope_peak_snr) }}</el-descriptions-item>
          <el-descriptions-item label="包络峭度">{{ fmt(result.features?.envelope_kurtosis) }}</el-descriptions-item>
        </el-descriptions>
      </section>
      <section class="panel">
        <div class="panel-title">轴承故障指示器</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item v-for="(val, name) in result.fault_indicators" :key="name" :label="name">
            <template v-if="val && typeof val === 'object'">
              <el-tag :type="val.significant ? 'danger' : val.warning ? 'warning' : 'success'" size="small">{{ val.significant ? '命中' : val.warning ? '预警' : '正常' }}</el-tag>
              <span v-if="val.snr" style="margin-left:4px">SNR={{ fmt(val.snr) }}</span>
              <span v-if="val.value" style="margin-left:4px">值={{ fmt(val.value) }}</span>
            </template>
            <template v-else>{{ fmt(val) }}</template>
          </el-descriptions-item>
        </el-descriptions>
      </section>
    </template>

    <!-- 齿轮方法 -->
    <template v-if="selectedMethodInfo?.category === 'gear'">
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

    <!-- 行星箱方法 -->
    <template v-if="selectedMethodInfo?.category === 'planetary'">
      <section class="panel">
        <div class="panel-title">{{ selectedMethodInfo.label }} 结果</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item v-for="(val, name) in filterPlanetaryResult" :key="name" :label="name">{{ fmt(val) }}</el-descriptions-item>
        </el-descriptions>
      </section>
      <section v-if="result.fault_indicators" class="panel">
        <div class="panel-title">故障指示器</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item v-for="(val, name) in result.fault_indicators" :key="name" :label="name">
            <template v-if="val && typeof val === 'object'">
              <el-tag :type="val.critical ? 'danger' : val.significant ? 'warning' : 'success'" size="small">{{ val.critical ? '严重' : val.significant ? '显著' : '正常' }}</el-tag>
            </template>
            <template v-else>{{ fmt(val) }}</template>
          </el-descriptions-item>
        </el-descriptions>
      </section>
    </template>
  </div>
</template>

<script setup>
import { fmt } from '../../composables/useResearchDiagnosis'

defineProps({
  result: { type: Object, required: true },
  selectedMethodInfo: { type: Object, default: null },
  filterPlanetaryResult: { type: Object, default: () => ({}) },
})
</script>

<style scoped>
.result-grid {
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

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  margin-bottom: 12px;
}

@media (max-width: 1100px) {
  .result-grid { grid-template-columns: 1fr; }
}
</style>
