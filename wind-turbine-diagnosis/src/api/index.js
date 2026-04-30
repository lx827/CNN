import {
  queryDeviceInfo,
  queryRealtimeVibration,
  queryDiagnosisResult,
  queryAlarmRecords,
  queryStatistics
} from '../database/virtual-db'

// 获取设备信息
export const getDeviceInfo = () => {
  return queryDeviceInfo()
}

// 获取实时振动数据
export const getRealtimeVibrationData = () => {
  return queryRealtimeVibration()
}

// 获取故障诊断结果
export const getFaultDiagnosisResult = () => {
  return queryDiagnosisResult()
}

// 获取历史告警记录
export const getHistoryAlarmList = () => {
  return queryAlarmRecords()
}

// 获取统计数据
export const getStatistics = () => {
  return queryStatistics()
}
