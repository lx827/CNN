<template>
  <div ref="chartRef" class="chart-container" :style="containerStyle"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, default: () => null },
  height: { type: [String, Number], default: 320 }
})

const chartRef = ref(null)
let instance = null

const containerStyle = computed(() => {
  const h = typeof props.height === 'number' ? `${props.height}px` : props.height
  return { height: h }
})

const initChart = () => {
  if (!chartRef.value || instance) return
  instance = echarts.init(chartRef.value)
  if (props.option) {
    instance.setOption(props.option, true)
  }
}

const onResize = () => {
  instance?.resize()
}

onMounted(() => {
  nextTick(() => initChart())
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  instance?.dispose()
  instance = null
})

watch(() => props.option, (newOpt) => {
  if (!instance) {
    initChart()
  } else if (newOpt) {
    instance.setOption(newOpt, true)
  }
}, { deep: true })
</script>

<style scoped>
.chart-container {
  width: 100%;
}
</style>
