import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getDeviceInfo } from '../api'

export const useDeviceStore = defineStore('device', () => {
  // ========== State ==========
  const deviceList = ref([])
  const selectedDeviceId = ref(null)
  const loading = ref(false)
  const alarmStats = ref({})

  // ========== Getters ==========
  const selectedDevice = computed(() =>
    deviceList.value.find(d => d.device_id === selectedDeviceId.value) || null
  )

  const onlineDevices = computed(() =>
    deviceList.value.filter(d => d.status !== 'offline')
  )

  const offlineDevices = computed(() =>
    deviceList.value.filter(d => d.status === 'offline')
  )

  // ========== Actions ==========
  async function loadDevices(force = false) {
    if (!force && deviceList.value.length > 0 && !loading.value) {
      // 已有缓存且未在加载中，直接返回（避免重复请求）
      return
    }
    loading.value = true
    try {
      const res = await getDeviceInfo()
      const data = res.data || {}
      deviceList.value = data.devices || []
      alarmStats.value = data.alarmStats || {}
      // 如果没有选中设备，默认选中第一个在线设备
      if (!selectedDeviceId.value && deviceList.value.length > 0) {
        const firstOnline = deviceList.value.find(d => d.status !== 'offline')
        selectedDeviceId.value = firstOnline?.device_id || deviceList.value[0].device_id
      }
    } finally {
      loading.value = false
    }
  }

  function selectDevice(deviceId) {
    selectedDeviceId.value = deviceId
  }

  function clearDevices() {
    deviceList.value = []
    selectedDeviceId.value = null
  }

  return {
    deviceList,
    selectedDeviceId,
    selectedDevice,
    onlineDevices,
    offlineDevices,
    alarmStats,
    loading,
    loadDevices,
    selectDevice,
    clearDevices,
  }
})
