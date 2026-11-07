// 实际Vue setup/watch/卸载，网络与ECharts替身；不触发现场硬件。
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { createRequire } = require('node:module')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')
const frontend = createRequire(path.resolve(__dirname, '../../wind-turbine-diagnosis/package.json'))
const vue = frontend('vue'), { parse, compileScript } = frontend('@vue/compiler-sfc')
const { descriptor } = parse(readFileSync(path.resolve(__dirname, '../../wind-turbine-diagnosis/src/views/Acquisition.vue'), 'utf8'))
const script = compileScript(descriptor, { id: 'live-test' }).content.replace(/^import .* from ['"].*['"]\r?\n/gm, '').replace('export default', 'globalThis.Component =')
const renderer = vue.createRenderer({ createElement: () => ({ children: [] }), createText: text => ({ text }), createComment: () => ({}), insert: (c, p) => p.children.push(c), remove() {}, setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, patchProp() {} })
const flush = async () => { await new Promise(resolve => setImmediate(resolve)); await vue.nextTick() }
const copy = x => JSON.parse(JSON.stringify(x))

function harness(overrides = {}) {
  const timers = new Set(), listeners = new Set(), charts = [], records = [], views = [], sessions = []
  let current = null, stops = 0, recordStops = 0
  const context = { ...vue, console, Date,
    setTimeout(fn) { timers.add(fn); return fn }, clearTimeout(fn) { timers.delete(fn) },
    window: { addEventListener: (_, fn) => listeners.add(fn), removeEventListener: (_, fn) => listeners.delete(fn) },
    ElMessage: { success() {}, warning() {} },
    echarts: { init() { const c = { disposed: false, setOption(o) { assert.equal(this.disposed, false); this.option = o }, resize() {}, dispose() { this.disposed = true } }; charts.push(c); return c } },
    getAcquisitionCapabilities: async () => ({ data: { sample_rates: [50, 2000, 4000, 5000, 10000, 100000] } }),
    getAcquisitionAgents: async () => ({ data: [
      { id: 'dc24', online: true, source: 'dc24_tcp', state: { version: 3, save_directory: 'D:/chosen', sample_rates: [50, 2000, 4000, 5000, 10000, 100000] } },
      { id: 'replay', online: true, source: 'recording_replay', state: { version: 3 } }] }),
    getAcquisitionJobs: async () => ({ data: [{ id: 'historical', status: 'completed', source: 'recording_replay' }] }),
    getCurrentLiveSession: async () => ({ data: null }),
    startLiveSession: async data => { sessions.push(data); current = { id: 'session', ...data, status: 'streaming', revision: 1, received_at: new Date().toISOString(), recording: null }; return { data: copy(current) } },
    getLiveSession: async () => ({ data: copy(current) }),
    getLiveView: async (_id, options) => {
      views.push(copy(options))
      return { data: { fresh: true, window_start: 0, window_end: 1, channels: [0, 1, 2, 3].map(channel => ({ channel, label: `CH${channel+1}`, waveform: options.waveform ? [[0, channel+101]] : [], ...(options.fft ? { fft: [[50, channel+5]] } : {}), ...(options.rms ? { rms: channel+1, mean: 0, rms_curve: [[0, channel+1]] } : {}), ...(options.envelope ? { envelope: [[2, channel+1]] } : {}) })) } }
    },
    startLiveRecording: async (_id, data) => { records.push(copy(data)); current.recording = { id: 'record', status: 'capturing', samples_per_channel: 0 }; return { data: { id: 'record' } } },
    stopLiveRecording: async () => { recordStops++; current.recording = { ...current.recording, status: 'completed' }; return {} },
    stopLiveSession: async () => { stops++; current.status = 'stopped'; return { data: copy(current) } },
    selectAcquisitionDirectory: async () => ({ data: { id: 'picker' } }),
    getAcquisitionDirectory: async () => ({ data: { id: 'picker', status: 'done', directory: 'E:/field recordings' } }),
    downloadAcquisitionFile: async () => {}, ...overrides }
  vm.runInNewContext(script, context, { filename: 'Acquisition.vue' })
  context.Component.render = function () {
    const state = vue.getCurrentInstance().setupState
    if (state.view?.channels) for (const c of state.view.channels) for (const kind of state.kinds) {
      state.bindChart(kind.key, c.channel, state.show[kind.key] ? { key: `${kind.key}-${c.channel}` } : null)
    }
    return vue.h('div')
  }
  const app = renderer.createApp(context.Component), instance = app.mount({ children: [] })
  return { app, state: instance.$.setupState, charts, timers, listeners, records, sessions, views,
    get stops() { return stops }, get recordStops() { return recordStops },
    async tick() { const fn = timers.values().next().value; assert.ok(fn); timers.delete(fn); await fn(); await flush() } }
}

test('打开页面不自动播放历史/回放；示波才请求实时数据且不创建保存任务', async t => {
  const h = harness(); t.after(() => h.app.unmount()); await flush()
  assert.equal(h.state.realAgents.length, 1)
  assert.equal(h.state.view, null); assert.equal(h.charts.length, 0)
  await h.state.startPreview(); await h.tick()
  assert.equal(h.records.length, 0); assert.equal(h.charts.length, 8)
  assert.equal(h.charts[0].option.series[0].data[0][1], 101)
})

test('长时采集从示波中开始；停止保存保持示波；手动模式无固定时长', async t => {
  const h = harness(); t.after(() => h.app.unmount()); await flush()
  h.state.form.duration = 3600; h.state.form.sample_rate = 4000
  await h.state.startRecording()
  assert.equal(h.records[0].duration, 3600); assert.equal(h.sessions[0].sample_rate, 4000)
  assert.equal(h.records[0].save_directory, 'D:/chosen')
  await h.state.stopRecording(); await h.tick()
  assert.equal(h.recordStops, 1); assert.equal(h.stops, 0); assert.equal(h.state.session.status, 'streaming')
  h.state.form.manual = true; await h.state.startRecording()
  assert.equal(h.records[1].duration, 0)
})

test('示波中可以切换显示并设置包络区间；非法频带不发包络请求或保存任务', async t => {
  const h = harness(); t.after(() => h.app.unmount()); await flush(); await h.state.startPreview(); await h.tick()
  h.state.show.envelope = true; await h.tick()
  assert.equal(h.views.at(-1).envelope, false)
  await h.state.startRecording(); assert.equal(h.records.length, 0)
  Object.assign(h.state.form, { band_low: 200, band_high: 800 }); h.state.show.rms = true; await h.tick()
  assert.equal(h.views.at(-1).envelope, true); assert.equal(h.views.at(-1).rms, true)
  assert.equal(h.views.at(-1).band_high, 800)
  for (const key of ['fft', 'rms', 'envelope', 'waveform']) h.state.show[key] = false
  await h.tick(); assert.equal(h.state.visibleKinds.length, 0)
})

test('现场目录选择结果用于保存，离开页面释放全部图表/轮询', async () => {
  const h = harness(); await flush(); await h.state.chooseDirectory(); await h.tick()
  assert.equal(h.state.form.save_directory, 'E:/field recordings')
  await h.state.startPreview(); await h.tick()
  h.app.unmount(); assert.ok(h.charts.every(c => c.disposed)); assert.equal(h.timers.size, 0); assert.equal(h.listeners.size, 0)
})

test('实时数据尚未返回时离开，不创建迟到图表或新的轮询', async () => {
  let resolve
  const h = harness({ getLiveView: () => new Promise(r => { resolve = r }) })
  await flush(); await h.state.startPreview()
  const pending = h.tick(); await flush(); h.app.unmount()
  resolve({ data: { channels: [{ channel: 0, waveform: [[0, 9]] }] } }); await pending
  assert.equal(h.charts.length, 0); assert.equal(h.timers.size, 0)
})

test('示波累计到1000秒后，横轴仍只显示当前窗口而不从0秒挤压波形', async t => {
  const h = harness({ getLiveView: async () => ({ data: { fresh: true, window_start: 1000, window_end: 1000.2,
    channels: [0, 1, 2, 3].map(channel => ({ channel, label: `CH${channel+1}`,
      waveform: [[1000, -100], [1000.1, 100], [1000.2, -100]], fft: [[0, 0], [50, 100]] })) } }) })
  t.after(() => h.app.unmount()); await flush(); await h.state.startPreview(); await h.tick()
  const axis = h.charts[0].option.xAxis
  assert.equal(axis.min, 'dataMin', '当前窗口不能被补上0秒起点')
  assert.equal(axis.max, 'dataMax')
})

test('后端重启后旧会话404，自动关联现有新会话而不创建替代采样', async t => {
  let resume = false
  const replacement = { id: 'replacement', sample_rate: 5000, status: 'streaming', revision: 2, received_at: new Date().toISOString() }
  const h = harness({
    getCurrentLiveSession: async () => ({ data: resume ? replacement : null }),
    getLiveSession: async id => { if (id === 'session') throw Object.assign(new Error('session gone'), { response: { status: 404 } }); return { data: replacement } }
  })
  t.after(() => h.app.unmount()); await flush(); await h.state.startPreview(); resume = true
  await h.tick()
  assert.equal(h.state.session.id, 'replacement')
  await h.tick(); assert.equal(h.charts.length, 8)
  assert.equal(h.sessions.length, 1, '重新关联不自动开始新硬件会话')
})
