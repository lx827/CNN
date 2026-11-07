<template>
  <el-card style="margin-top: 20px">
    <template #header>
      <div class="card-header">
        <span>通道级振动特征告警阈值</span>
        <el-text type="info" size="small">当任一通道的振动特征超过阈值时自动生成告警</el-text>
      </div>
    </template>

    <el-form label-width="160px">
      <!-- 指标说明 -->
      <el-alert
        type="info"
        :closable="false"
        style="margin-bottom: 20px; max-width: 700px"
      >
        <div style="line-height: 1.8;">
          <strong>阈值规则：</strong>预警值 < 严重值，留空表示不启用该指标告警。<br/>
          <strong>均方根：</strong>反映振动能量；<strong>峰值：</strong>反映冲击程度；<br/>
          <strong>峭度：</strong>反映冲击性（正常≈3，故障时显著增大）；<br/>
          <strong>峰值因子：</strong>反映信号的冲击特征（正常≈3~5）。
        </div>
      </el-alert>

      <div v-for="(item, key) in thresholdItems" :key="key" style="max-width: 700px">
        <el-divider v-if="key !== 'rms'" />
        <el-row :gutter="16">
          <el-col :span="6">
            <el-form-item :label="item.label" style="margin-bottom: 12px;">
              <el-switch
                v-model="thresholdEnabled[key]"
                active-text="启用"
                inactive-text="禁用"
              />
            </el-form-item>
          </el-col>
          <el-col :span="9">
            <el-form-item label="预警阈值" style="margin-bottom: 12px;">
              <el-input-number
                v-model="thresholds[key].warning"
                :disabled="!thresholdEnabled[key]"
                :min="0"
                :step="item.step"
                :precision="item.precision"
                controls-position="right"
                style="width: 160px"
                placeholder="不启用"
              />
            </el-form-item>
          </el-col>
          <el-col :span="9">
            <el-form-item label="严重阈值" style="margin-bottom: 12px;">
              <el-input-number
                v-model="thresholds[key].critical"
                :disabled="!thresholdEnabled[key]"
                :min="0"
                :step="item.step"
                :precision="item.precision"
                controls-position="right"
                style="width: 160px"
                placeholder="不启用"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </div>

      <el-form-item style="margin-top: 16px;">
        <el-button type="primary" :loading="savingThresholds" @click="$emit('save')">
          <el-icon><Check /></el-icon>
          保存阈值配置
        </el-button>
        <el-button @click="$emit('reset')">重置</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
defineProps({
  thresholds: { type: Object, required: true },
  thresholdEnabled: { type: Object, required: true },
  thresholdItems: { type: Object, required: true },
  savingThresholds: { type: Boolean, default: false },
})

defineEmits(['save', 'reset'])
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 16px;
}
</style>
