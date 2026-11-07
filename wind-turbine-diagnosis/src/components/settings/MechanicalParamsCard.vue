<template>
  <el-card style="margin-top: 20px">
    <template #header>
      <div class="card-header">
        <span>机械参数配置</span>
        <el-text type="info" size="small">用于阶次跟踪与故障诊断</el-text>
      </div>
    </template>

    <el-form label-width="160px" style="max-width: 700px">
      <el-alert
        type="info"
        :closable="false"
        style="margin-bottom: 16px"
      >
        配置齿轮齿数和轴承几何参数后，系统可在频谱/包络/阶次分析中自动标定故障特征频率。
      </el-alert>

      <el-tabs v-model="activeChannel">
        <el-tab-pane
          v-for="i in form.channel_count"
          :key="i"
          :label="channelNames[i] || `通道${i}`"
          :name="String(i)"
        >
          <el-divider content-position="left">齿轮参数</el-divider>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="输入轴齿数">
                <el-input-number
                  v-model="form.gear_teeth[String(i)].input"
                  :min="1"
                  :max="200"
                  :step="1"
                  controls-position="right"
                  style="width: 140px"
                  placeholder="未配置"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="输出轴齿数">
                <el-input-number
                  v-model="form.gear_teeth[String(i)].output"
                  :min="1"
                  :max="200"
                  :step="1"
                  controls-position="right"
                  style="width: 140px"
                  placeholder="未配置"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-divider content-position="left">轴承参数</el-divider>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="滚子数 n">
                <el-input-number
                  v-model="form.bearing_params[String(i)].n"
                  :min="1"
                  :max="50"
                  :step="1"
                  controls-position="right"
                  style="width: 140px"
                  placeholder="未配置"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="滚子直径 d (mm)">
                <el-input-number
                  v-model="form.bearing_params[String(i)].d"
                  :min="0.1"
                  :max="100"
                  :step="0.01"
                  :precision="2"
                  controls-position="right"
                  style="width: 140px"
                  placeholder="未配置"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="节径 D (mm)">
                <el-input-number
                  v-model="form.bearing_params[String(i)].D"
                  :min="1"
                  :max="500"
                  :step="0.01"
                  :precision="2"
                  controls-position="right"
                  style="width: 140px"
                  placeholder="未配置"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="接触角 α (°)">
                <el-input-number
                  v-model="form.bearing_params[String(i)].alpha"
                  :min="0"
                  :max="45"
                  :step="1"
                  controls-position="right"
                  style="width: 140px"
                  placeholder="未配置"
                />
              </el-form-item>
            </el-col>
          </el-row>
        </el-tab-pane>
      </el-tabs>

      <el-divider />
      <el-form-item>
        <el-button type="primary" :loading="savingMechanical" @click="$emit('save')">
          <el-icon><Check /></el-icon>
          保存机械参数
        </el-button>
        <el-button @click="$emit('reset')">重置</el-button>
        <el-button type="warning" @click="$emit('sync')">
          <el-icon><CopyDocument /></el-icon>
          一键同步到所有通道
        </el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
defineProps({
  form: { type: Object, required: true },
  channelNames: { type: Object, default: () => ({}) },
  savingMechanical: { type: Boolean, default: false },
})

const activeChannel = defineModel('activeChannel', { type: String, default: '1' })

defineEmits(['save', 'reset', 'sync'])
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
