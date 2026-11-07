<template>
  <div class="dashboard">
    <!-- 告警统计卡片 -->
    <SummaryCards
      :total="devices.length"
      :normal="normalCount"
      :warning="warningCount"
      :fault="faultCount"
      :offline="offlineCount"
    />

    <!-- 设备健康度卡片列表 -->
    <DeviceCardList
      :devices="devices"
      :selected-id="selectedDevice?.deviceId"
      @select="selectDevice"
    />

    <!-- 选中设备的详细图表 -->
    <template v-if="selectedDevice">
      <el-row :gutter="20" class="charts-row">
        <el-col :xs="24" :md="12">
          <el-card>
            <template #header>
              <div class="card-header">
                <span>{{ selectedDevice.deviceName }} — 健康度仪表盘</span>
              </div>
            </template>
            <div ref="gaugeChart" class="chart"></div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card>
            <template #header>
              <div class="card-header">
                <span>{{ selectedDevice.deviceName }} — 故障类型分布</span>
              </div>
            </template>
            <div ref="pieChart" class="chart"></div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 部件状态表 -->
      <el-row>
        <el-col :span="24">
          <el-card>
            <template #header>
              <div class="card-header">
                <span>{{ selectedDevice.deviceName }} — 部件状态详情</span>
              </div>
            </template>
            <el-table :data="selectedDevice.components || []" stripe>
              <el-table-column prop="name" label="部件名称" />
              <el-table-column label="状态" width="120">
                <template #default="{ row }">
                  <el-tag :type="getStatusType(row.status)">
                    {{ getStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="健康度" width="300">
                <template #default="{ row }">
                  <span v-if="row.status === 'offline'" class="offline-health">
                    <el-icon><Warning /></el-icon> 离线，暂无数据
                  </span>
                  <el-progress
                    v-else
                    :percentage="row.health || 0"
                    :color="getHealthColor(row.health || 0)"
                    :stroke-width="18"
                  />
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
import SummaryCards from '../components/dashboard/SummaryCards.vue'
import DeviceCardList from '../components/dashboard/DeviceCardList.vue'
import { useDashboard } from '../composables/useDashboard'

const {
  devices, selectedDevice, normalCount, warningCount, faultCount, offlineCount,
  gaugeChart, pieChart, loadData, selectDevice, getStatusType, getStatusText, getHealthColor,
} = useDashboard()
</script>

<style scoped>
.dashboard {
  padding: 0;
}

.charts-row {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 16px;
}

.offline-health {
  font-size: 13px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 4px;
}

.chart {
  height: 350px;
  width: 100%;
}
</style>
