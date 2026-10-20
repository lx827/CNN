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

test('总览推送和轮询共享在途请求，保留一次后续刷新', async t => {
  const pending = []
  let initial = true
  const h = harness(() => {
    if (initial) { initial = false; return Promise.resolve(result(80)) }
    return new Promise((resolve, reject) => pending.push({ resolve, reject }))
  })
  t.after(() => h.app.unmount())
  await flush()
  const finished = h.state.loadData()
  h.listeners.get('device_online')()
  h.listeners.get('device_offline')()
  for (const poll of h.timers) poll()
  assert.equal(pending.length, 1, '慢请求尚未完成时不能并发查询总览')
  pending[0].resolve(result(70))
  await flush()
  assert.equal(pending.length, 2, '在途推送不能被丢弃，也不能逐事件排队')
  pending[1].resolve(result(40))
  await finished
  assert.equal(h.state.selectedDevice.healthScore, 40)
})

test('总览卸载后丢弃在途响应和待刷新事件', async () => {
  let calls = 0
  const pending = []
  const h = harness(() => {
    calls++
    if (calls === 1) return Promise.resolve(result(80))
    return new Promise(done => pending.push(done))
  })
  await flush()
  const finished = h.state.loadData()
  h.listeners.get('device_online')()
  h.app.unmount()
  pending.forEach(resolve => resolve(result(40)))
  await finished
  assert.equal(calls, 2)
  assert.equal(h.state.selectedDevice.healthScore, 80)
})

test('总览请求失败仍处理后续推送，失败后可以再次刷新', async t => {
  let calls = 0, reject
  const h = harness(() => {
    calls++
    if ([2, 4].includes(calls)) return new Promise((_, fail) => { reject = fail })
    return Promise.resolve(result(calls === 1 ? 80 : 40))
  })
  t.after(() => h.app.unmount())
  await flush()
  const finished = h.state.loadData().catch(error => error)
  h.listeners.get('device_online')()
  reject(new Error('受控网络失败'))
  assert.equal(await finished, undefined, '已收到新推送时必须继续刷新')
  assert.equal(h.state.selectedDevice.healthScore, 40)
  const failed = h.state.loadData()
  const rejected = assert.rejects(failed, /独立请求失败/)
  reject(new Error('独立请求失败'))
  await rejected
  await h.state.loadData()
  assert.equal(calls, 5, '失败不能锁死刷新队列')
})
