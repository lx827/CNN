const test = require('node:test')
const assert = require('node:assert/strict')

test('研究请求只传组合参数，CVS显式缺参及合法采集记录可区分', async () => {
  const { buildCompositeRequest } = await import('../src/utils/compositeResearch.js')
  assert.deepEqual(buildCompositeRequest('composite_mswpee', null), { method: 'composite_mswpee', options: {} })
  const missing = buildCompositeRequest('composite_cvs_med_msb', 2)
  assert.equal(missing.rot_freq_hz, 2)
  assert.equal('alignment' in missing, false)
  assert.throws(() => buildCompositeRequest('composite_cvs_med_msb', 2, '{'), /合法JSON/)
  assert.throws(() => buildCompositeRequest('composite_cvs_med_msb', 2, '[]'), /JSON对象/)
  const context = { carrier_phase_rad: [0, 1], planet_phase_rad: [0, 2], selected_planet: 0 }
  assert.deepEqual(buildCompositeRequest('composite_cvs_med_msb', 2, JSON.stringify(context)).alignment, context)
})

test('空值、中间失败和近似态保持中性，AM/FM及MSB图的单位分离', async () => {
  const { compositeValue, compositeStages, compositeReason, compositeCurves } = await import('../src/utils/compositeResearch.js')
  assert.equal(compositeValue(null), '—')
  assert.equal(compositeValue(0), '0')
  assert.equal(compositeStages({ analysis: { stages: [{ name: 'MED', status: 'approximate', reason: 'MED_not_converged' }] } })[0].state, '近似计算')
  assert.match(compositeReason('missing_spatial_passage_and_planet_phase_alignment'), /无法重组/)
  const curves = compositeCurves({ analysis: { data: { demodulation: {
    amplitude_spectrum: { points: [[8, .4]], axis_unit: 'Hz', amplitude_unit: 'input_signal' },
    frequency_spectrum: { points: [[8, 5]], axis_unit: 'Hz', amplitude_unit: 'Hz' },
  }, msb: { data: { slice: { modulation_frequency_hz: [8, 16], magnitude: [1, null], amplitude_unit: 'input_signal^4' } } } } } })
  assert.equal(curves[0].amplitude_unit, 'input_signal')
  assert.equal(curves[1].amplitude_unit, 'Hz')
  assert.equal(curves[2].amplitude_unit, 'input_signal^4')
  assert.deepEqual(curves[2].points, [[8, 1], [16, null]])
})

test('真实Vue研究组件渲染五种组合、阶段错误和未知诊断，不展示为正常', async () => {
  const { createServer } = await import('vite')
  const server = await createServer({ configFile: false,
    root: require('node:path').resolve(__dirname, '..'),
    plugins: [(await import('@vitejs/plugin-vue')).default()],
    server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: component } = await server.ssrLoadModule('/src/components/research/CompositeResult.vue')
    const { createSSRApp } = await import('vue')
    const { renderToString } = await import('@vue/server-renderer')
    const ElementPlus = (await import('element-plus')).default
    for (const method of ['composite_vmd_amfm', 'composite_msb', 'composite_cvs_med_msb', 'composite_vmd_ica', 'composite_mswpee']) {
      const result = { analysis_method: method, evaluation_status: 'not_evaluable', diagnosis_conclusion: 'unknown',
        analysis: { status: 'indeterminate', reason: 'missing_spatial_passage_and_planet_phase_alignment',
          stages: [{ name: 'CVS', status: 'indeterminate', reason: 'missing_spatial_passage_and_planet_phase_alignment' }], metrics: { raw: null }, data: {} },
        evaluation: { reason: 'research_combination_has_no_validated_fault_thresholds' } }
      const app = createSSRApp(component, { result })
      app.use(ElementPlus)
      const html = await renderToString(app)
      assert.match(html, /仅供研究|研究组合/)
      assert.match(html, /故障结论未知/)
      assert.match(html, /不参与生产评分/)
      assert.match(html, /不可判定/)
      assert.match(html, /无法重组/)
      assert.doesNotMatch(html, />正常</)
    }
  } finally { await server.close() }
})
