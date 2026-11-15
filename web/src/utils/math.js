/**
 * 数学计算工具函数
 */

export function calcRms(arr) {
  if (!arr || arr.length === 0) return 0
  const sum = arr.reduce((s, v) => s + v * v, 0)
  return Math.sqrt(sum / arr.length)
}

export function calcPeak(arr) {
  if (!arr || arr.length === 0) return 0
  return Math.max(...arr.map(Math.abs))
}
