// 使用实际 Vue setup/watch/卸载逻辑；隔离网络和图表，不触发现场采集。
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { createRequire } = require('node:module')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')
const requireFrontend = createRequire(path.resolve(__dirname, '../../wind-turbine-diagnosis/package.json'))
const vue = requireFrontend('vue')
const { parse, compileScript } = requireFrontend('@vue/compiler-sfc')
const { descriptor } = parse(readFileSync(path.resolve(__dirname, '../../wind-turbine-diagnosis/src/views/Acquisition.vue'), 'utf8'))
const script = compileScript(descriptor, { id: 'acquisition-test' }).content
  .replace(/^import .* from ['"].*['"]\r?\n/gm, '').replace('export default', 'globalThis.Component =')
const renderer = vue.createRenderer({
  createElement: () => ({ children: [] }), createText: text => ({ text }), createComment: () => ({}),
  insert: (child, parent) => parent.children.push(child), remove() {}, setText() {}, setElementText() {},
  parentNode: () => null, nextSibling: () => null, patchProp() {}
})
const flush = async () => { await new Promise(resolve => setImmediate(resolve)); await vue.nextTick() }
const completed = { id: 'a'.repeat(32), source: 'dc24_tcp', status: 'completed', sample_rate: 5000, duration: 1,
  metadata: { samples_per_channel: 5080 }, analysis_options: { fft: true, rms: false, envelope: false } }
const result = { duration: 1.016, channels: [0, 1, 2, 3].map(channel => ({
  channel, label: `CH${channel+1}`, waveform: [[0, channel]], fft: [[1, channel+1]]
})) }

function harness(overrides = {}) {
  const timers = new Set(), listeners = new Set(), charts = [], submitted = []
  let current = completed
  const context = { ...vue, console,
    setTimeout(fn) { timers.add(fn); return fn }, clearTimeout(fn) { timers.delete(fn) },
    window: { addEventListener: (_, fn) => listeners.add(fn), removeEventListener: (_, fn) => listeners.delete(fn) },
    ElMessage: { success() {} },
    echarts: { init() { const chart = { disposed: false, setOption(o) { assert.equal(this.disposed, false); this.option = o }, dispose() { this.disposed = true }, resize() {} }; charts.push(chart); return chart } },
    getAcquisitionAgents: async () => ({ data: [{ id: 'dc24', online: true, source: 'dc24_tcp', state: { sample_rates: [2000, 5000] } }] }),
    getAcquisitionJobs: async () => ({ data: [] }),
    getAcquisition: async () => ({ data: current }),
    createAcquisition: async data => { submitted.push(data); current = { ...completed, ...data, analysis_options: data.analysis, status: 'pending', metadata: null }; return { data: current } },
    getAcquisitionAnalysis: async () => ({ data: result }),
    getAcquisitionWaveform: async (_id, params) => ({ data: [[params.start, params.channel+7]] }),
    stopAcquisition: async () => ({ data: { ...current, cancel_requested: true } }),
    downloadAcquisitionFile: async () => {}, ...overrides }
  vm.runInNewContext(script, context, { filename: 'Acquisition.vue' })
  context.Component.render = function () {
    const state = vue.getCurrentInstance().setupState
    for (const ref of ['waveChart', 'fftChart', 'rmsChart', 'envelopeChart']) state[ref] = { ref }
    state.formRef = { validate: async () => {
      let error
      state.bandRules[0].validator(null, null, value => { error = value })
      if (error) throw error
      return true
    } }
    return vue.h('div')
  }
  const app = renderer.createApp(context.Component)
  const instance = app.mount({ children: [] })
  return { app, state: instance.$.setupState, charts, timers, listeners, submitted }
}

test('可取消全部分析，并原样发送时长和采样率', async t => {
  const h = harness(); t.after(() => h.app.unmount()); await flush()
  Object.assign(h.state.form, { duration: 23, sample_rate: 5000, fft: false, rms: false, envelope: false })
  await h.state.startCapture()
  assert.equal(h.submitted.length, 1)
  assert.equal(h.submitted[0].duration, 23)
  assert.equal(h.submitted[0].sample_rate, 5000)
  assert.deepEqual(JSON.parse(JSON.stringify(h.submitted[0].analysis)), { fft: false, rms: false, envelope: false, band_low: null, band_high: null })
  await h.state.stopCapture()
  assert.equal(h.state.job.cancel_requested, true)
})

test('包络频带必须由用户填写，越过Nyquist边界不得创建任务', async t => {
  const h = harness(); t.after(() => h.app.unmount()); await flush()
  Object.assign(h.state.form, { envelope: true, band_low: undefined, band_high: undefined })
  await h.state.startCapture(); assert.equal(h.submitted.length, 0)
  Object.assign(h.state.form, { band_low: 100, band_high: 2500 })
  await h.state.startCapture(); assert.equal(h.submitted.length, 0)
  Object.assign(h.state.form, { band_low: 200, band_high: 800 })
  await h.state.startCapture(); assert.equal(h.submitted[0].analysis.band_high, 800)
})

test('完成任务自动画所选图，切换通道后卸载释放图表与轮询', async () => {
  const h = harness(); await flush(); await h.state.selectJob(completed); await flush()
  assert.equal(h.charts.length, 2, '只创建波形和已选择的FFT')
  assert.equal(h.charts[0].option.series[0].data[0][1], 7)
  h.state.selectedChannel = 2; await flush()
  assert.equal(h.charts[0].option.series[0].data[0][1], 9)
  h.app.unmount()
  assert.ok(h.charts.every(c => c.disposed))
  assert.equal(h.timers.size, 0)
  assert.equal(h.listeners.size, 0)
})

test('原始区间请求乱序返回时保留最后选择的区间', async t => {
  const pending = []
  let hold = false
  const h = harness({ getAcquisitionWaveform: async (_id, params) => hold ? new Promise(resolve => pending.push({ params, resolve })) : ({ data: [[0, 1]] }) })
  t.after(() => h.app.unmount()); await flush(); await h.state.selectJob(completed)
  hold = true
  h.state.waveStart = .1; const first = h.state.loadWaveform()
  h.state.waveStart = .3; const second = h.state.loadWaveform()
  pending[1].resolve({ data: [[.3, 30]] }); await second
  pending[0].resolve({ data: [[.1, 10]] }); await first
  assert.equal(h.state.waveform[0][0], .3)
})
