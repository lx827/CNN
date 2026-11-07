<template>
  <div class="monitor">
    <!-- 传感器状态和运行参数 -->
    <el-row :gutter="20" class="sensor-row">
      <el-col :xs="24" :md="16">
        <SensorStatusCard
          v-model:selected-device="selectedCollectDevice"
          :sensors="sensors"
          :devices="collectDevices"
          :is-collecting="isCollecting"
          :collection-status="collectionStatus"
          :last-data-source="lastDataSource"
          @collect="requestCollect"
        />
      </el-col>
      <el-col :xs="24" :md="8">
        <RunParamsCard
          v-model="selectedMonitorDevice"
          :params="params"
          :devices="collectDevices"
          @change="onMonitorDeviceChange"
        />
      </el-col>
    </el-row>

    <!-- 采集进度提示 -->
    <el-row v-if="isCollecting" :gutter="20" class="progress-row">
      <el-col :span="24">
        <CollectionProgress :status="collectionStatus" :progress="collectionProgress" />
      </el-col>
    </el-row>

    <!-- 振动信号图表 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>振动信号时域波形</span>
              <el-select v-model="activeChannel" style="width: 220px">
                <el-option
                  v-for="(channel, index) in channels"
                  :key="index"
                  :label="channel.name"
                  :value="index"
                />
              </el-select>
            </div>
          </template>
          <div ref="timeDomainChart" class="chart"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="chart-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>频域谱图</span>
              <el-tag v-if="lastDataSource === 'special'" type="danger" size="small" effect="plain">特殊采集数据</el-tag>
            </div>
          </template>
          <div ref="frequencyChart" class="chart"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import SensorStatusCard from '../components/monitor/SensorStatusCard.vue'
import RunParamsCard from '../components/monitor/RunParamsCard.vue'
import CollectionProgress from '../components/monitor/CollectionProgress.vue'
import { useMonitor } from '../composables/useMonitor'

const {
  activeChannel, channels, params, sensors, timeDomainChart, frequencyChart,
  isCollecting, collectionStatus, collectionProgress, lastDataSource,
  collectDevices, selectedCollectDevice, selectedMonitorDevice,
  requestCollect, startPolling, onMonitorDeviceChange,
} = useMonitor()
</script>

<style scoped>
.monitor {
  padding: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 16px;
}

.sensor-row {
  margin-bottom: 20px;
}

.progress-row {
  margin-bottom: 20px;
}

.chart-row {
  margin-bottom: 20px;
}

.chart {
  height: 300px;
  width: 100%;
}
</style>
