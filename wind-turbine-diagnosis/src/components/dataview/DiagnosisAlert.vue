<template>
  <el-row v-if="diagnosis" :gutter="16">
    <el-col :span="24">
      <el-alert
        :title="`批次诊断：${view.label}`"
        :type="view.alertType"
        :description="description"
        show-icon
        :closable="false"
        style="margin-bottom: 16px"
      />
    </el-col>
  </el-row>
</template>

<script setup>
import { computed } from 'vue'
import { getDiagnosisView } from '../../utils/diagnosisStatus'
const props = defineProps({
  diagnosis: { type: Object, default: null },
  description: { type: String, default: '' },
})
const view = computed(() => getDiagnosisView(props.diagnosis))
</script>
