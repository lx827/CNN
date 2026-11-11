const test = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const diagnosis = (conclusion, score = 90) => ({
  contract_version: 1, evaluation_status: 'evaluated', diagnosis_conclusion: conclusion,
  health_score: score, coverage: 'complete', evaluations: [],
})
const unavailable = state => ({ evaluation_status: state, diagnosis_conclusion: 'unknown', health_score: null, coverage: 'none' })

test('完整两维契约保留零分，非法值与缺失证据不被展示为正常或故障', async () => {
  const { getDiagnosisView } = await import('../src/utils/diagnosisStatus.js')
  for (const [conclusion, tone] of [['normal', 'success'], ['warning', 'warning'], ['fault', 'danger']]) {
    assert.equal(getDiagnosisView(diagnosis(conclusion)).tone, tone)
  }
  assert.equal(getDiagnosisView(diagnosis('fault', 0)).scoreText, '0.0')
  for (const value of [null, undefined, '', 'normal', {}, { status: 'normal', health_score: 100 },
    diagnosis('unknown'), diagnosis('__proto__'), diagnosis('future'), diagnosis('normal', null),
    diagnosis('normal', '100'), diagnosis('fault', Infinity), diagnosis('normal', 101),
    { ...diagnosis('normal'), evaluation_status: 'future' },
    { ...unavailable('indeterminate'), diagnosis_conclusion: 'fault' },
    unavailable('indeterminate'), unavailable('not_evaluable')]) {
    assert.equal(getDiagnosisView(value).tone, 'info')
    assert.equal(getDiagnosisView(value).scoreText, '-')
  }
  const local = { object_id: 'bearing', evaluation_status: 'evaluated', diagnosis_conclusion: 'warning' }
  assert.equal(getDiagnosisView(local).tone, 'warning')
  assert.equal(getDiagnosisView(local).scoreText, '-')
})

test('Dashboard和Monitor API读模型保留真实诊断，缺失通道不能继承设备评分', async () => {
  const runApi = async (file, backend, extra = {}) => {
    const source = readFileSync(path.resolve(__dirname, '../src/api', file), 'utf8')
      .replace(/^import .*\r?\n/gm, '').replace(/^export /gm, '')
    const context = { ...extra, request: { get: async () => backend } }
    vm.runInNewContext(source + '\nglobalThis.api = { ' + (file === 'dashboard.js' ? 'getDeviceInfo' : 'getRealtimeVibrationData') + ' }', context)
    return context.api
  }
  const device = { device_id: 'D1', name: '设备1', channel_count: 2, ...diagnosis('fault', 0), is_offline: true }
  const dashboard = await runApi('dashboard.js', { data: { devices: [device], diagnosis: { D1: diagnosis('fault', 0) } } })
  const row = (await dashboard.getDeviceInfo()).data.devices[0]
  assert.equal(row.health_score, 0)
  assert.equal(row.diagnosis_conclusion, 'fault')
  assert.equal(row.is_offline, true)
  assert.ok(row.components.every(component => component.health_score === undefined))
  const unknown = unavailable('not_evaluable')
  const monitor = await runApi('monitor.js', { data: [{ channel: 2, data: [999], ...unknown, is_offline: false }] }, { calcRms: () => 999, calcPeak: () => 999 })
  const channel = (await monitor.getRealtimeVibrationData()).data.channels[0]
  assert.equal(channel.evaluation_status, 'not_evaluable')
  assert.equal(channel.health_score, null)
  assert.equal(channel.rms, 999)
})

test('真实Vue明细、综合分析、批次头和设备卡统一渲染中性状态及部分覆盖', async () => {
  const { createServer } = await import('vite')
  const server = await createServer({ configFile: false,
    root: path.resolve(__dirname, '..'), logLevel: 'error',
    plugins: [(await import('@vitejs/plugin-vue')).default()],
    server: { middlewareMode: true, hmr: false }, appType: 'custom' })
  try {
    const { createSSRApp } = await import('vue')
    const { renderToString } = await import('@vue/server-renderer')
    const { default: ElementPlus, ID_INJECTION_KEY, ZINDEX_INJECTION_KEY } = await import('element-plus')
    const icons = await import('@element-plus/icons-vue')
    const render = (component, props) => {
      const app = createSSRApp(component, props).use(ElementPlus)
      app.provide(ID_INJECTION_KEY, { prefix: 100, current: 0 })
      app.provide(ZINDEX_INJECTION_KEY, { current: 0 })
      for (const [name, icon] of Object.entries(icons)) app.component(name, icon)
      return renderToString(app)
    }
    const targets = [
      ['DiagnosisDetail.vue', result => ({ diagnosis: result })],
      ['dataview/ComprehensiveSection.vue', result => ({ computedFullAnalysis: true, fullAnalysisData: result })],
      ['dataview/DetailHeader.vue', result => ({ batch: result })],
      ['dashboard/DeviceCardList.vue', result => ({ devices: [{ deviceId: 'D1', ...result }] })],
    ]
    const cases = [
      [diagnosis('normal'), '正常', 'success'], [diagnosis('warning'), '预警', 'warning'], [diagnosis('fault', 0), '故障', 'danger'],
      [unavailable('indeterminate'), '不可判定', 'info'], [unavailable('not_evaluable'), '不可评估', 'info'],
      [{}, '未知', 'info'], [{ ...diagnosis('normal'), evaluation_status: 'future' }, '未知', 'info'],
    ]
    for (const [file, props] of targets) {
      const { default: component } = await server.ssrLoadModule('/src/components/' + file)
      for (const [result, label, tone] of cases) {
        const html = await render(component, props(result))
        assert.ok(html.includes(label), `${file}: ${label}`)
        assert.match(html, new RegExp(`el-(?:tag|text)--${tone}|el-alert--${tone === 'danger' ? 'error' : tone}`))
        if (tone === 'info') assert.doesNotMatch(html, />正常<|>故障<|健康度[^<]*100|健康度[^<]*0\.0/)
      }
    }
    const { default: component } = await server.ssrLoadModule('/src/components/DiagnosisDetail.vue')
    const partial = { ...diagnosis('warning', 72), coverage: 'partial', evaluations: [
      { object_id: 'bearing', evaluation_status: 'evaluated', diagnosis_conclusion: 'warning' },
      { object_id: 'gear', evaluation_status: 'indeterminate', diagnosis_conclusion: 'unknown', reason: 'insufficient_evidence' },
    ] }
    const html = await render(component, { diagnosis: partial })
    assert.match(html, /部分对象形成有效评估/)
    assert.match(html, /bearing/)
    assert.match(html, /gear/)
    assert.match(html, /不可判定/)
    assert.match(html, /72\.0/)
  } finally { await server.close() }
})
