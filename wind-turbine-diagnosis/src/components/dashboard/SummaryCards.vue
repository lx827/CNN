<template>
  <el-row :gutter="16" class="summary-row">
    <el-col :xs="12" :sm="8" :md="8" :lg="4">
      <el-card class="summary-card">
        <div class="card-content">
          <el-icon :size="32" color="#165DFF"><Cpu /></el-icon>
          <div class="card-info">
            <div class="label">设备总数</div>
            <div class="value">{{ total }}</div>
          </div>
        </div>
      </el-card>
    </el-col>
    <el-col :xs="12" :sm="8" :md="8" :lg="5">
      <el-card class="summary-card">
        <div class="card-content">
          <el-icon :size="32" color="#52C41A"><CircleCheck /></el-icon>
          <div class="card-info">
            <div class="label">诊断正常</div>
            <div class="value" style="color: #52C41A">{{ normal }}</div>
          </div>
        </div>
      </el-card>
    </el-col>
    <el-col :xs="12" :sm="8" :md="8" :lg="5">
      <el-card class="summary-card">
        <div class="card-content">
          <el-icon :size="32" color="#FAAD14"><Warning /></el-icon>
          <div class="card-info">
            <div class="label">预警设备</div>
            <div class="value" style="color: #FAAD14">{{ warning }}</div>
          </div>
        </div>
      </el-card>
    </el-col>
    <el-col :xs="12" :sm="8" :md="8" :lg="5">
      <el-card class="summary-card">
        <div class="card-content">
          <el-icon :size="32" color="#F5222D"><Delete /></el-icon>
          <div class="card-info">
            <div class="label">故障设备</div>
            <div class="value" style="color: #F5222D">{{ fault }}</div>
          </div>
        </div>
      </el-card>
    </el-col>
    <el-col :xs="12" :sm="8" :md="8" :lg="5">
      <el-card class="summary-card">
        <div class="card-content">
          <el-icon :size="32" color="#909399"><Warning /></el-icon>
          <div class="card-info">
            <div class="label">离线设备</div>
            <div class="value" style="color: #909399">{{ offline }}</div>
          </div>
        </div>
      </el-card>
    </el-col>
    <el-col :xs="12" :sm="8" :md="8" :lg="4">
      <el-card class="summary-card"><div class="card-info">
        <div class="label">诊断未知 / 不可评估</div><div class="value">{{ unknown }}</div>
      </div></el-card>
    </el-col>
  </el-row>
</template>

<script setup>
defineProps({
  total: { type: Number, default: 0 },
  normal: { type: Number, default: 0 },
  warning: { type: Number, default: 0 },
  fault: { type: Number, default: 0 },
  offline: { type: Number, default: 0 },
  unknown: { type: Number, default: 0 },
})
</script>

<style scoped>
.summary-row {
  margin-bottom: 20px;
}

.summary-card {
  border-radius: 8px;
  transition: all 0.3s;
}

.summary-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
}

.card-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.card-info {
  flex: 1;
}

.card-info .label {
  font-size: 13px;
  color: #666;
  margin-bottom: 6px;
}

.card-info .value {
  font-size: 28px;
  font-weight: bold;
  color: #333;
}
</style>
