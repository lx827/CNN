const test = require("node:test")
const assert = require("node:assert/strict")

test("行星设置保留完整几何与参考轴，切回定轴移除行星字段", async () => {
  const { mechanicalGearForm, mechanicalGearPayload } = await import("../src/utils/planetaryDiagnosis.js")
  const config = { sun: 28, ring: 100, planet: 36, planet_count: 4, reference_axis: "sun", fixed_member: "ring" }
  const form = mechanicalGearForm(config)
  assert.equal(form.gear_type, "planetary")
  assert.deepEqual(mechanicalGearPayload(form), { gear_type: "planetary", ...config })
  assert.deepEqual(mechanicalGearPayload({ ...form, gear_type: "fixed_axis", input: 18, output: 27 }), { input: 18, output: 27 })
})

test("不可评估保留空值和具体理由，不把原始指标展示为告警", async () => {
  const { planetaryMetricRows, planetaryReasonText } = await import("../src/utils/planetaryDiagnosis.js")
  const rows = planetaryMetricRows({ metrics: { fm4: { status: "not_evaluable", value: null, reason: "missing_comparable_planetary_variance_history" } }, sideband_analysis: { ser: { status: "evaluated", value: 0 } } })
  assert.equal(rows[0].value, 0)
  assert.equal(rows[1].value, null)
  assert.match(planetaryReasonText("missing_comparable_planetary_baseline"), /不能判断健康或故障/)
})
