<template>
  <div class="settings-page">
    <!-- 边端采集配置 -->
    <EdgeConfigCard
      v-model:interval-value="intervalValue"
      v-model:interval-unit="intervalUnit"
      v-model:apply-edge-to-all="applyEdgeToAll"
      :form="form"
      :device-list="deviceList"
      :channel-names="channelNames"
      :computed-seconds="computedSeconds"
      :saving-edge="savingEdge"
      @device-change="onDeviceChange"
      @save="onSaveEdgeConfig"
      @reset="onReset"
    />

    <!-- 机械参数配置（齿轮/轴承） -->
    <MechanicalParamsCard
      v-model:active-channel="activeMechanicalChannel"
      :form="form"
      :channel-names="channelNames"
      :saving-mechanical="savingMechanical"
      @save="onSaveMechanical"
      @reset="onReset"
      @sync="onSyncMechanical"
    />

    <!-- 告警阈值配置 -->
    <ThresholdsCard
      :thresholds="thresholds"
      :threshold-enabled="thresholdEnabled"
      :threshold-items="thresholdItems"
      :saving-thresholds="savingThresholds"
      @save="onSaveThresholds"
      @reset="onResetThresholds"
    />

    <!-- 配置说明 -->
    <ConfigNotesCard />
  </div>
</template>

<script setup>
import EdgeConfigCard from '../components/settings/EdgeConfigCard.vue'
import MechanicalParamsCard from '../components/settings/MechanicalParamsCard.vue'
import ThresholdsCard from '../components/settings/ThresholdsCard.vue'
import ConfigNotesCard from '../components/settings/ConfigNotesCard.vue'
import { useSettings, thresholdItems } from '../composables/useSettings'

const {
  deviceList, form, channelNames, activeMechanicalChannel, applyEdgeToAll,
  intervalValue, intervalUnit, computedSeconds,
  thresholds, thresholdEnabled,
  savingEdge, savingMechanical, savingThresholds,
  onDeviceChange, onSaveEdgeConfig, onReset,
  onSaveMechanical, onSyncMechanical, onSaveThresholds, onResetThresholds,
} = useSettings()
</script>

<style scoped>
.settings-page {
  padding: 0;
}
</style>
