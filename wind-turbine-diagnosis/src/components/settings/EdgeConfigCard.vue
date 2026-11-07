<template>
  <el-card>
    <template #header>
      <div class="card-header">
        <span>边端采集配置</span>
        <el-text type="info" size="small">修改后约 30 秒内同步到边端</el-text>
      </div>
    </template>

    <el-form :model="form" label-width="160px" style="max-width: 600px">
      <!-- 设备选择 -->
      <el-form-item label="选择设备">
        <el-select v-model="form.device_id" style="width: 240px" @change="$emit('device-change')">
          <el-option
            v-for="dev in deviceList"
            :key="dev.device_id"
            :label="dev.name"
            :value="dev.device_id"
          />
        </el-select>
      </el-form-item>

      <el-divider />

      <!-- 上传间隔 -->
      <el-form-item label="自动采集间隔">
        <div style="display: flex; align-items: center; gap: 8px;">
          <el-input-number
            v-model="intervalValue"
            :min="1"
            :max="999"
            :step="1"
            controls-position="right"
            style="width: 140px"
          />
          <el-select v-model="intervalUnit" style="width: 100px">
            <el-option
              v-for="u in unitOptions"
              :key="u.value"
              :label="u.label"
              :value="u.value"
            />
          </el-select>
        </div>
        <el-text type="info" size="small">
          边端每隔 <strong>{{ intervalValue }} {{ unitOptions.find(u=>u.value===intervalUnit).label }}</strong>
          （共 {{ computedSeconds }} 秒）自动上传一批数据
        </el-text>
      </el-form-item>

      <!-- 轮询间隔 -->
      <el-form-item label="任务轮询间隔">
        <el-slider
          v-model="form.task_poll_interval"
          :min="3"
          :max="60"
          :step="1"
          show-stops
          show-input
          style="width: 400px"
        />
        <el-text type="info" size="small">边端每隔多少秒查询一次云端采集任务（范围 3~60 秒）</el-text>
      </el-form-item>

      <el-divider />

      <!-- 只读信息 -->
      <el-form-item label="采样率">
        <el-input-number
          v-model="form.sample_rate"
          :min="1000"
          :max="100000"
          :step="100"
          controls-position="right"
          style="width: 200px"
        />
        <el-text type="info" size="small" style="margin-left: 8px;">Hz，修改后约 30 秒同步到边端</el-text>
      </el-form-item>

      <el-form-item label="采集时长">
        <el-input-number
          v-model="form.window_seconds"
          :min="1"
          :max="60"
          controls-position="right"
          style="width: 200px"
        />
        <el-text type="info" size="small" style="margin-left: 8px;">秒，修改后约 30 秒同步到边端</el-text>
      </el-form-item>

      <el-form-item label="通道数">
        <el-input-number
          v-model="form.channel_count"
          :min="1"
          :max="8"
          controls-position="right"
          style="width: 200px"
        />
        <el-text type="info" size="small" style="margin-left: 8px;">修改后约 30 秒同步到边端</el-text>
      </el-form-item>

      <!-- 通道名称配置 -->
      <el-form-item label="通道名称">
        <div style="display: flex; flex-direction: column; gap: 8px;">
          <div v-for="i in form.channel_count" :key="i" style="display: flex; align-items: center; gap: 8px;">
            <el-text type="info" size="small" style="width: 50px;">通道{{ i }}</el-text>
            <el-input
              v-model="channelNames[i]"
              placeholder="输入通道名称"
              style="width: 200px"
              size="small"
            />
          </div>
        </div>
        <el-text type="info" size="small">通道名称将显示在监测和告警页面中</el-text>
      </el-form-item>

      <el-divider />

      <!-- 数据压缩配置（云端控制边端） -->
      <el-form-item label="数据压缩">
        <el-switch
          v-model="form.compression_enabled"
          active-text="启用"
          inactive-text="关闭"
        />
        <el-text type="info" size="small" style="margin-left: 8px;">
          关闭后上传原始数据（不压缩），网络占用更高
        </el-text>
      </el-form-item>

      <el-form-item label="压缩比">
        <el-input-number
          v-model="form.downsample_ratio"
          :min="1"
          :max="20"
          :step="1"
          controls-position="right"
          style="width: 140px"
          :disabled="!form.compression_enabled"
        />
        <el-text type="info" size="small" style="margin-left: 8px;">
          1=不压缩，8=8倍压缩（81920点→10240点）
        </el-text>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="savingEdge" @click="$emit('save')">
          <el-icon><Check /></el-icon>
          保存采集配置
        </el-button>
        <el-button @click="$emit('reset')">重置</el-button>
        <el-checkbox v-model="applyEdgeToAll" style="margin-left: 16px;">
          应用到所有设备
        </el-checkbox>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { unitOptions } from '../../composables/useSettings'

defineProps({
  form: { type: Object, required: true },
  deviceList: { type: Array, default: () => [] },
  channelNames: { type: Object, default: () => ({}) },
  computedSeconds: { type: Number, default: 0 },
  savingEdge: { type: Boolean, default: false },
})

const intervalValue = defineModel('intervalValue', { type: Number, default: 10 })
const intervalUnit = defineModel('intervalUnit', { type: String, default: 'second' })
const applyEdgeToAll = defineModel('applyEdgeToAll', { type: Boolean, default: false })

defineEmits(['device-change', 'save', 'reset'])
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
