<template>
  <el-row v-if="status === 'fault' || status === 'warning'" :gutter="16">
    <el-col :span="24">
      <el-alert
        :title="status === 'fault' ? '⚠️ 该批次被诊断为故障状态' : '⚡ 该批次被诊断为预警状态'"
        :type="status === 'fault' ? 'error' : 'warning'"
        :description="description"
        show-icon
        :closable="false"
        style="margin-bottom: 16px"
      />
    </el-col>
  </el-row>
</template>

<script setup>
const props = defineProps({
  status: { type: String, default: '' },
  description: { type: String, default: '' },
})
</script>
