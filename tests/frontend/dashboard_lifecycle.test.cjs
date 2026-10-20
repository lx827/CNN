// 真实 Vue 生命周期验证总览页资源释放与选中设备刷新。
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { createRequire } = require('node:module')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')
const requireFrontend = createRequire(path.resolve(__dirname, '../../wind-turbine-diagnosis/package.json'))
const vue = requireFrontend('vue')
const { parse, compileScript } = requireFrontend('@vue/compiler-sfc')
const { descriptor } = parse(readFileSync(path.resolve(__dirname, '../../wind-turbine-diagnosis/src/views/Dashboard.vue'), 'utf8'))
const script = compileScript(descriptor, { id: 'dashboard-test' }).content
  .replace(/^import .* from ['"].*['"]\r?\n/gm, '')
  .replace('export default', 'globalThis.Dashboard =')
const renderer = vue.createRenderer({
  createElement: () => ({ children: [] }), createText: () => ({}), createComment: () => ({}),
  insert: (child, parent) => parent.children.push(child), remove() {}, setText() {}, setElementText() {},
  parentNode: () => null, nextSibling: () => null, patchProp() {}
})
const flush = async () => { await new Promise(resolve => setImmediate(resolve)); await vue.nextTick() }

function harness(fetchData) {
  const timers = new Set(), listeners = new Map(), resize = new Set(), charts = []
  const context = {
    ...vue, console,
    getDeviceInfo: fetchData,
    setInterval: callback => { timers.add(callback); return callback },
    clearInterval: callback => timers.delete(callback),
    window: { addEventListener: (_, cb) => resize.add(cb), removeEventListener: (_, cb) => resize.delete(cb) },
    getWebSocketClient: () => ({ connect() {}, on(event, cb) {
      listeners.set(event, cb)
      return () => listeners.delete(event)
    } }),
    echarts: { init() {
      const chart = { disposed: false, setOption() { assert.equal(this.disposed, false) }, resize() {}, dispose() { this.disposed = true } }
      charts.push(chart)
      return chart
    } }
  }
  vm.runInNewContext(script, context)
  context.Dashboard.render = () => {
    const state = vue.getCurrentInstance().setupState
    state.gaugeChart = {}; state.pieChart = {}
    return vue.h('div')
  }
  const app = renderer.createApp(context.Dashboard)
  const page = app.mount({ children: [] })
  return { app, state: page.$.setupState, timers, listeners, resize, charts }
}
const result = score => ({ data: { devices: [{ deviceId: 'TEST', status: 'normal', healthScore: score }], alarmStats: {} } })

test('离开总览页清理轮询、图表和订阅', async () => {
  const h = harness(async () => result(80))
  await flush()
  assert.equal(h.timers.size, 1)
  h.app.unmount()
  assert.equal(h.timers.size, 0)
  assert.equal(h.listeners.size, 0)
  assert.equal(h.resize.size, 0)
  assert.ok(h.charts.every(chart => chart.disposed))
})

test('请求未完成时离开，不在卸载后建立轮询和图表', async () => {
  let resolve
  const h = harness(() => new Promise(done => { resolve = done }))
  h.app.unmount()
  resolve(result(80))
  await flush()
  assert.equal(h.timers.size, 0)
  assert.equal(h.listeners.size, 0)
  assert.equal(h.charts.length, 0)
})

test('刷新时更新选中的设备，后端 critical 正确计入故障', async t => {
  let score = 80
  const h = harness(async () => {
    const value = result(score)
    value.data.devices[0].status = 'critical'
    return value
  })
  t.after(() => h.app.unmount())
  await flush()
  score = 40
  await h.state.loadData()
  await flush()
  assert.equal(h.state.selectedDevice.healthScore, 40)
  assert.equal(h.state.faultCount, 1)
  assert.equal(h.state.getStatusText('critical'), '故障')
})
