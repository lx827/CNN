const reasons = {
  missing_comparable_planetary_baseline: "缺少可比健康基线，尚不能判断健康或故障",
  incompatible_planetary_baseline: "健康基线与当前几何、速度或分析表示不一致",
  planetary_demodulation_requires_explicit_constant_speed: "当前行星解调仅接受明确恒速，变速补偿未迁移",
  missing_planetary_reference_axis_or_fixed_member: "请配置转速参考轴和固定构件",
  missing_complete_planetary_geometry: "行星齿数和轮数配置不完整",
  carrier_sidebands_not_resolvable: "记录长度不足以分辨行星架边带",
  event_orders_not_resolvable: "事件候选阶次尚不可分辨",
  missing_comparable_planetary_variance_history: "缺少可比健康方差历史",
  no_observable_nonsynchronous_energy: "未观察到可测的非同步残差能量",
  no_measurable_local_background: "局部背景不可测，未计算幅值背景比",
}

export const planetaryReasonText = reason => reasons[reason] || reason || ""
export const planetaryAxisText = axis => ({ sun: "太阳轴", carrier: "行星架" })[axis] || "未配置"
export const planetaryCandidateText = name => ({
  sun_mesh_encounter: "太阳轮局部啮合事件候选", planet_single_mesh: "行星轮单啮合事件候选",
  planet_two_mesh: "行星轮双啮合事件候选", ring_mesh_encounter: "齿圈局部啮合事件候选",
  carrier_transfer: "行星架传递路径调制",
})[name] || name

export function planetaryMetricRows(result = {}) {
  const rows = Object.entries(result.metrics || {}).map(([name, metric]) => ({ name: name.toUpperCase(), ...metric }))
  if (result.sideband_analysis?.ser) rows.unshift({ ...result.sideband_analysis.ser, name: "SER（行星架间隔）" })
  return rows
}

export function mechanicalGearForm(config = {}) {
  return { ...config, gear_type: config.gear_type || (config.sun != null || config.ring != null ? "planetary" : "fixed_axis") }
}

export function mechanicalGearPayload(config = {}) {
  if (config.gear_type === "planetary") {
    return Object.fromEntries(["gear_type", "sun", "ring", "planet", "planet_count", "reference_axis", "fixed_member"].map(key => [key, config[key] ?? null]))
  }
  return { input: config.input ?? null, output: config.output ?? null }
}
