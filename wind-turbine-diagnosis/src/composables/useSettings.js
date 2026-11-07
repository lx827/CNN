/**
 * Settings 边端配置页状态与保存逻辑
 *
 * 职责:设备列表/配置/阈值三级加载,边端采集配置、通道级机械参数、
 *       告警阈值的保存与同步,采集间隔的数值+单位双向解析。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getDevices, getDeviceConfig, updateDeviceConfig, updateBatchDeviceConfig,
  getAlarmThresholds, updateAlarmThresholds,
} from '../api/devices'

// 采集间隔单位选项(value: 单位值,factor: 换算到秒的系数)
export const unitOptions = [
  { label: '秒', value: 'second', factor: 1 },
  { label: '分钟', value: 'minute', factor: 60 },
  { label: '小时', value: 'hour', factor: 3600 },
]

// 阈值指标定义(与后端 DEFAULT_THRESHOLDS 保持一致,基于真实 .npy 数据校准)
export const thresholdItems = {
  rms: { label: '均方根', step: 0.001, precision: 3 },
  peak: { label: '峰值', step: 0.001, precision: 3 },
  kurtosis: { label: '峭度', step: 0.1, precision: 1 },
  crest_factor: { label: '峰值因子', step: 0.1, precision: 1 },
}

// 将秒反向解析为友好数值+单位
const parseInterval = (seconds) => {
  if (seconds >= 3600 && seconds % 3600 === 0) {
    return { value: seconds / 3600, unit: 'hour' }
  }
  if (seconds >= 60 && seconds % 60 === 0) {
    return { value: seconds / 60, unit: 'minute' }
  }
  return { value: seconds, unit: 'second' }
}

export function useSettings() {
  const deviceList = ref([])
  const savingEdge = ref(false)
  const savingMechanical = ref(false)
  const savingThresholds = ref(false)

  const form = ref({
    device_id: 'WTG-001',
    upload_interval: 10,
    task_poll_interval: 5,
    sample_rate: 25600,
    window_seconds: 10,
    channel_count: 3,
    gear_teeth: {},
    bearing_params: {},
    compression_enabled: true,
    downsample_ratio: 8,
  })

  // 当前正在编辑的机械参数通道
  const activeMechanicalChannel = ref('1')

  // 一键同步目标通道
  const syncTargetChannels = ref([])

  const applyEdgeToAll = ref(false)

  // 通道名称
  const channelNames = ref({ 1: '轴承附近', 2: '驱动端', 3: '风扇端' })

  // 上传间隔的数值与单位（支持 秒/分钟/小时）
  const intervalValue = ref(10)
  const intervalUnit = ref('second')

  // 计算总秒数（显示用）
  const computedSeconds = computed(() => {
    const factor = unitOptions.find(u => u.value === intervalUnit.value)?.factor || 1
    return intervalValue.value * factor
  })

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

      // 加载齿轮/轴承参数（兼容旧格式设备级与新格式通道级）
      const chCount = form.value.channel_count || 3
      const gt = d.gear_teeth || {}
      const bp = d.bearing_params || {}

      // 判断是否为旧格式（顶层含业务字段）
      const isOldGear = 'input' in gt || 'output' in gt
      const isOldBearing = 'n' in bp || 'd' in bp || 'D' in bp || 'alpha' in bp

      for (let i = 1; i <= chCount; i++) {
        const ch = String(i)
        if (isOldGear) {
          form.value.gear_teeth[ch] = { input: gt.input ?? null, output: gt.output ?? null }
        } else {
          const chGt = gt[ch] || {}
          form.value.gear_teeth[ch] = { input: chGt.input ?? null, output: chGt.output ?? null }
        }
        if (isOldBearing) {
          form.value.bearing_params[ch] = { n: bp.n ?? null, d: bp.d ?? null, D: bp.D ?? null, alpha: bp.alpha ?? null }
        } else {
          const chBp = bp[ch] || {}
          form.value.bearing_params[ch] = { n: chBp.n ?? null, d: chBp.d ?? null, D: chBp.D ?? null, alpha: chBp.alpha ?? null }
        }
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

  const onSaveEdgeConfig = async () => {
    savingEdge.value = true
    try {
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
        compression_enabled: form.value.compression_enabled,
        downsample_ratio: form.value.downsample_ratio,
      }
      if (applyEdgeToAll.value) {
        await updateBatchDeviceConfig(payload)
        ElMessage.success('采集配置已批量应用到所有设备，约 30 秒内同步到边端')
      } else {
        await updateDeviceConfig(form.value.device_id, payload)
        ElMessage.success('采集配置已保存，约 30 秒内同步到边端')
      }
    } catch (e) {
      console.error('保存采集配置失败:', e)
      ElMessage.error('保存采集配置失败')
    } finally {
      savingEdge.value = false
    }
  }

  const onSaveMechanical = async () => {
    savingMechanical.value = true
    try {
      const payload = {
        gear_teeth: form.value.gear_teeth,
        bearing_params: form.value.bearing_params,
      }
      await updateDeviceConfig(form.value.device_id, payload)
      ElMessage.success('机械参数已保存')
    } catch (e) {
      console.error('保存机械参数失败:', e)
      ElMessage.error('保存机械参数失败')
    } finally {
      savingMechanical.value = false
    }
  }

  const onReset = () => {
    loadConfig()
  }

  const onSyncMechanical = () => {
    const src = activeMechanicalChannel.value
    const srcGear = form.value.gear_teeth[src]
    const srcBearing = form.value.bearing_params[src]
    for (let i = 1; i <= form.value.channel_count; i++) {
      const ch = String(i)
      if (ch === src) continue
      form.value.gear_teeth[ch] = { ...srcGear }
      form.value.bearing_params[ch] = { ...srcBearing }
    }
    ElMessage.success(`已将 ${channelNames.value[src] || '通道' + src} 的机械参数同步到所有通道`)
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

  return {
    deviceList,
    form,
    channelNames,
    activeMechanicalChannel,
    syncTargetChannels,
    applyEdgeToAll,
    intervalValue,
    intervalUnit,
    computedSeconds,
    thresholds,
    thresholdEnabled,
    savingEdge,
    savingMechanical,
    savingThresholds,
    onDeviceChange,
    onSaveEdgeConfig,
    onReset,
    onSaveMechanical,
    onSyncMechanical,
    onSaveThresholds,
    onResetThresholds,
  }
}
