<template>
  <div class="settings-page">
    <!-- 边端采集配置 -->
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
          <el-select v-model="form.device_id" style="width: 240px" @change="onDeviceChange">
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
          <el-button type="primary" :loading="saving" @click="onSave">
            <el-icon><Check /></el-icon>
            保存配置
          </el-button>
          <el-button @click="onReset">重置</el-button>
          <el-checkbox v-model="applyToAll" style="margin-left: 16px;">
            应用到所有设备
          </el-checkbox>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 机械参数配置（齿轮/轴承） -->
    <el-card style="margin-top: 20px">
      <template #header>
        <div class="card-header">
          <span>机械参数配置</span>
          <el-text type="info" size="small">用于阶次跟踪与故障诊断</el-text>
        </div>
      </template>

      <el-form :model="form" label-width="160px" style="max-width: 600px">
        <el-alert
          type="info"
          :closable="false"
          style="margin-bottom: 16px"
        >
          配置齿轮齿数和轴承几何参数后，系统可在频谱/包络/阶次分析中自动标定故障特征频率。
        </el-alert>

        <el-divider content-position="left">齿轮参数</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="输入轴齿数">
              <el-input-number
                v-model="form.gear_teeth.input"
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
                v-model="form.gear_teeth.output"
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
                v-model="form.bearing_params.n"
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
                v-model="form.bearing_params.d"
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
                v-model="form.bearing_params.D"
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
                v-model="form.bearing_params.alpha"
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

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="onSave">
            <el-icon><Check /></el-icon>
            保存配置
          </el-button>
          <el-button @click="onReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 告警阈值配置 -->
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
            <strong>RMS：</strong>均方根，反映振动能量；<strong>Peak：</strong>峰值，反映冲击程度；<br/>
            <strong>Kurtosis：</strong>峭度，反映冲击性（正常≈3，故障时显著增大）；<br/>
            <strong>Crest Factor：</strong>峰值因子，反映信号的冲击特征（正常≈3~5）。
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
          <el-button type="primary" :loading="savingThresholds" @click="onSaveThresholds">
            <el-icon><Check /></el-icon>
            保存阈值配置
          </el-button>
          <el-button @click="onResetThresholds">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 配置说明 -->
    <el-card style="margin-top: 20px">
      <template #header>
        <span>配置说明</span>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="自动采集间隔">
          边端在无人干预的情况下，每隔该时间自动采集并上传一批振动数据。
          值越小数据越实时，但网络负载越高；值越大越节省带宽。
        </el-descriptions-item>
        <el-descriptions-item label="任务轮询间隔">
          边端每隔该时间向云端查询一次是否有手动触发的采集任务。
          该值应小于等于自动采集间隔，确保手动任务能被及时响应。
        </el-descriptions-item>
        <el-descriptions-item label="同步机制">
          边端每 30 秒自动拉取一次云端配置。保存后，最长等待 30 秒即可生效。
          也可重启边端客户端立即生效。
        </el-descriptions-item>
        <el-descriptions-item label="告警阈值">
          通道级阈值配置针对每个通道独立判断。当同一批数据中多个通道同时超标时，
          系统会分别生成多条通道级告警。诊断结果类告警（健康度/故障概率）不受此配置影响。
        </el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getDevices, getDeviceConfig, updateDeviceConfig, updateBatchDeviceConfig,
  getAlarmThresholds, updateAlarmThresholds
} from '../api'

const deviceList = ref([])
const saving = ref(false)
const savingThresholds = ref(false)

const form = ref({
  device_id: 'WTG-001',
  upload_interval: 10,
  task_poll_interval: 5,
  sample_rate: 25600,
  window_seconds: 10,
  channel_count: 3,
  gear_teeth: { input: null, output: null },
  bearing_params: { n: null, d: null, D: null, alpha: null },
  compression_enabled: true,
  downsample_ratio: 8,
})

const applyToAll = ref(false)

// 通道名称
const channelNames = ref({ 1: '轴承附近', 2: '驱动端', 3: '风扇端' })

// 上传间隔的数值与单位（支持秒/分钟/小时）
const intervalValue = ref(10)
const intervalUnit = ref('second')

const unitOptions = [
  { label: '秒', value: 'second', factor: 1 },
  { label: '分钟', value: 'minute', factor: 60 },
  { label: '小时', value: 'hour', factor: 3600 },
]

// 计算总秒数（显示用）
const computedSeconds = computed(() => {
  const factor = unitOptions.find(u => u.value === intervalUnit.value)?.factor || 1
  return intervalValue.value * factor
})

// 将秒数反向解析为友好数值+单位
const parseInterval = (seconds) => {
  if (seconds >= 3600 && seconds % 3600 === 0) {
    return { value: seconds / 3600, unit: 'hour' }
  }
  if (seconds >= 60 && seconds % 60 === 0) {
    return { value: seconds / 60, unit: 'minute' }
  }
  return { value: seconds, unit: 'second' }
}

// 阈值配置（与后端 DEFAULT_THRESHOLDS 保持一致，基于真实 .npy 数据校准）
const thresholds = ref({
  rms: { warning: 0.015, critical: 0.030 },
  peak: { warning: 0.100, critical: 0.150 },
  kurtosis: { warning: 5.5, critical: 7.0 },
  crest_factor: { warning: 9.0, critical: 10.5 },
})

const thresholdEnabled = ref({
  rms: true,
  peak: true,
  kurtosis: true,
  crest_factor: true,
})

const thresholdItems = {
  rms: { label: 'RMS 均方根', step: 0.001, precision: 3 },
  peak: { label: 'Peak 峰值', step: 0.001, precision: 3 },
  kurtosis: { label: 'Kurtosis 峭度', step: 0.1, precision: 1 },
  crest_factor: { label: 'Crest Factor 峰值因子', step: 0.1, precision: 1 },
}

const loadDevices = async () => {
  const res = await getDevices()
  deviceList.value = (res.data || []).map(d => ({
    device_id: d.device_id,
    name: d.name || d.device_id
  }))
}

const loadConfig = async () => {
  try {
    const res = await getDeviceConfig(form.value.device_id)
    const d = res.data || {}
    form.value.upload_interval = d.upload_interval ?? 10
    form.value.task_poll_interval = d.task_poll_interval ?? 5
    form.value.sample_rate = d.sample_rate ?? 25600
    form.value.window_seconds = d.window_seconds ?? 10
    form.value.channel_count = d.channel_count ?? 3
    form.value.compression_enabled = d.compression_enabled ?? true
    form.value.downsample_ratio = d.downsample_ratio ?? 8

    // 加载齿轮/轴承参数
    const gt = d.gear_teeth || {}
    form.value.gear_teeth = {
      input: gt.input ?? null,
      output: gt.output ?? null,
    }
    const bp = d.bearing_params || {}
    form.value.bearing_params = {
      n: bp.n ?? null,
      d: bp.d ?? null,
      D: bp.D ?? null,
      alpha: bp.alpha ?? null,
    }

    // 加载通道名称
    const names = d.channel_names || {}
    for (let i = 1; i <= 8; i++) {
      channelNames.value[i] = names[String(i)] || `通道${i}`
    }

    const parsed = parseInterval(form.value.upload_interval)
    intervalValue.value = parsed.value
    intervalUnit.value = parsed.unit
  } catch (e) {
    console.error('加载配置失败:', e)
    ElMessage.error('加载配置失败')
  }
}

const loadThresholds = async () => {
  try {
    const res = await getAlarmThresholds(form.value.device_id)
    const userCfg = res.data?.alarm_thresholds || {}
    const effective = res.data?.effective_thresholds || {}
    for (const key of Object.keys(thresholdItems)) {
      const t = userCfg[key] || {}
      const eff = effective[key] || {}
      // 显示实际生效的值（含默认值回退），但标记是否为自定义
      thresholds.value[key] = {
        warning: eff.warning !== null && eff.warning !== undefined ? eff.warning : null,
        critical: eff.critical !== null && eff.critical !== undefined ? eff.critical : null,
      }
      // 只有用户显式配置了该指标才标记为启用
      thresholdEnabled.value[key] = t.warning !== null || t.critical !== null
    }
  } catch (e) {
    console.error('加载阈值失败:', e)
    ElMessage.error('加载阈值配置失败')
  }
}

const onDeviceChange = () => {
  loadConfig()
  loadThresholds()
}

const onSave = async () => {
  saving.value = true
  try {
    // 构建通道名称对象
    const names = {}
    for (let i = 1; i <= form.value.channel_count; i++) {
      names[String(i)] = channelNames.value[i] || `通道${i}`
    }
    const payload = {
      upload_interval: computedSeconds.value,
      task_poll_interval: form.value.task_poll_interval,
      sample_rate: form.value.sample_rate,
      window_seconds: form.value.window_seconds,
      channel_count: form.value.channel_count,
      channel_names: names,
      gear_teeth: form.value.gear_teeth,
      bearing_params: form.value.bearing_params,
      compression_enabled: form.value.compression_enabled,
      downsample_ratio: form.value.downsample_ratio,
    }
    if (applyToAll.value) {
      await updateBatchDeviceConfig(payload)
      ElMessage.success('配置已批量应用到所有设备，约 30 秒内同步到边端')
    } else {
      await updateDeviceConfig(form.value.device_id, payload)
      ElMessage.success('配置已保存，约 30 秒内同步到边端')
    }
    ElMessage.success('配置已保存，约 30 秒内同步到边端')
  } catch (e) {
    console.error('保存配置失败:', e)
    ElMessage.error('保存配置失败')
  } finally {
    saving.value = false
  }
}

const onReset = () => {
  loadConfig()
}

const onSaveThresholds = async () => {
  // 校验：预警 < 严重
  for (const [key, item] of Object.entries(thresholdItems)) {
    if (!thresholdEnabled.value[key]) continue
    const w = thresholds.value[key].warning
    const c = thresholds.value[key].critical
    if (w !== null && c !== null && w >= c) {
      ElMessage.error(`${item.label} 的预警阈值必须小于严重阈值`)
      return
    }
  }

  savingThresholds.value = true
  try {
    const payload = {}
    for (const key of Object.keys(thresholdItems)) {
      payload[key] = thresholdEnabled.value[key]
        ? {
            warning: thresholds.value[key].warning,
            critical: thresholds.value[key].critical,
          }
        : { warning: null, critical: null }
    }
    await updateAlarmThresholds(form.value.device_id, payload)
    ElMessage.success('告警阈值已保存')
  } catch (e) {
    console.error('保存阈值失败:', e)
    ElMessage.error('保存阈值失败')
  } finally {
    savingThresholds.value = false
  }
}

const onResetThresholds = () => {
  loadThresholds()
}

onMounted(async () => {
  await loadDevices()
  await loadConfig()
  await loadThresholds()
})
</script>

<style scoped>
.settings-page {
  padding: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 16px;
}
</style>
