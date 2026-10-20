// 使用真实 Vue 生命周期运行 Monitor，替换网络与图表以隔离云端数据。
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { createRequire } = require('node:module')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')

const frontendRequire = createRequire(path.resolve(__dirname, '../../wind-turbine-diagnosis/package.json'))
const vue = frontendRequire('vue')
const { parse, compileScript } = frontendRequire('@vue/compiler-sfc')
const source = readFileSync(path.resolve(__dirname, '../../wind-turbine-diagnosis/src/views/Monitor.vue'), 'utf8')
const { descriptor } = parse(source)
const script = compileScript(descriptor, { id: 'monitor-lifecycle-test' }).content
  .replace(/^import .* from ['"].*['"]\r?\n/gm, '')
  .replace('export default', 'globalThis.Monitor =')

const renderer = vue.createRenderer({
  createElement: () => ({ children: [] }),
  createText: text => ({ text }),
  createComment: () => ({}),
  insert: (child, parent) => parent.children.push(child),
  remove: () => {},
  setText: () => {},
  setElementText: () => {},
  parentNode: () => null,
  nextSibling: () => null,
  patchProp: () => {}
})

const channels = [0, 1].map(index => ({
  id: index + 1,
  name: `通道${index + 1}`,
  timeDomain: [index + 1, -1, 0.5],
  frequency: [0.1, index + 0.2],
  fftFreq: [0, 1],
  sampleRate: 8192,
  rms: 0.5
}))

const flush = async () => {
  await new Promise(resolve => setImmediate(resolve))
  await vue.nextTick()
}

function createHarness({ devicesPromise } = {}) {
  const charts = []
  const listeners = new Map()
  const resizeListeners = new Set()
  let requests = 0
  let connected = false
  const socket = {
    on(event, callback) {
      if (!listeners.has(event)) listeners.set(event, new Set())
      listeners.get(event).add(callback)
    },
    off: (event, callback) => listeners.get(event)?.delete(callback),
    connect: () => { connected = true },
    close: () => { connected = false }
  }
  const context = {
    ...vue,
    console,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    window: {
      addEventListener: (_event, callback) => resizeListeners.add(callback),
      removeEventListener: (_event, callback) => resizeListeners.delete(callback)
    },
    echarts: {
      init(element) {
        assert.ok(element, '图表初始化需要已挂载的容器')
        const chart = {
          option: {},
          disposed: false,
          setOption(option) {
            assert.equal(this.disposed, false, '已销毁的图表不能继续更新')
            this.option = { ...this.option, ...option }
          },
          resize() {},
          dispose() { this.disposed = true }
        }
        charts.push(chart)
        return chart
      },
      graphic: { LinearGradient: function () {} }
    },
    getDevices: () => devicesPromise || Promise.resolve({ data: [{ device_id: 'WTG-001' }] }),
    getRealtimeVibrationData: async () => {
      requests++
      return { data: { channels, sensorParams: { estimated_rpm: 1200 } } }
    },
    requestCollection: async () => { throw new Error('本测试禁止创建采集任务') },
    getTaskStatus: async () => { throw new Error('本测试禁止查询采集任务') },
    getWebSocketClient: () => socket,
    ElMessage: { success() {}, warning() {}, error() {} }
  }
  vm.runInNewContext(script, context, { filename: 'Monitor.vue' })
  // 只替换模板容器；setup、异步挂载、watch 和卸载使用实际组件代码与 Vue 运行时。
  context.Monitor.render = function () {
    const state = vue.getCurrentInstance().setupState
    state.timeDomainChart = { type: 'time-container' }
    state.frequencyChart = { type: 'frequency-container' }
    return vue.h('div')
  }
  return {
    charts,
    listeners,
    resizeListeners,
    get requests() { return requests },
    get connected() { return connected },
    mount() {
      const app = renderer.createApp(context.Monitor)
      const instance = app.mount({ children: [] })
      return { app, state: instance.$.setupState }
    }
  }
}

function assertWaveforms(charts) {
  assert.equal(charts.length, 2)
  assert.deepEqual(Array.from(charts[0].option.series[0].data), channels[0].timeDomain,
    '首次进入应自动显示默认通道时域波形，无需切换通道')
  assert.deepEqual(Array.from(charts[1].option.series[0].data), channels[0].frequency,
    '首次进入应自动显示频谱')
}

test('首次进入显示默认通道，切换通道仍正常', async t => {
  const harness = createHarness()
  const page = harness.mount()
  t.after(() => page.app.unmount())
  await flush()
  assertWaveforms(harness.charts)
  page.state.activeChannel = 1
  await vue.nextTick()
  assert.deepEqual(Array.from(harness.charts[0].option.series[0].data), channels[1].timeDomain)
})

test('离开后清理图表和订阅，重新进入无需手动刷新', async () => {
  const harness = createHarness()
  const first = harness.mount()
  await flush()
  first.app.unmount()
  assert.ok(harness.charts.every(chart => chart.disposed), '离开页面应释放图表')
  assert.equal(harness.resizeListeners.size, 0, '离开页面应移除 resize 监听')
  assert.equal(harness.connected, false, '离开页面应关闭连接')
  assert.equal([...harness.listeners.values()].reduce((total, items) => total + items.size, 0), 0,
    '单例 WebSocket 不应保留旧页面订阅')
  const second = harness.mount()
  try {
    await flush()
    assertWaveforms(harness.charts.slice(2))
    const before = harness.requests
    for (const callback of harness.listeners.get('sensor_update')) callback({})
    await flush()
    assert.equal(harness.requests, before + 1, '返回页面后一次推送只触发一次请求')
  } finally {
    second.app.unmount()
  }
})

test('数据尚未返回就离开页面，不应在卸载后创建图表或连接', async () => {
  let resolveDevices
  const devicesPromise = new Promise(resolve => { resolveDevices = resolve })
  const harness = createHarness({ devicesPromise })
  const page = harness.mount()
  page.app.unmount()
  resolveDevices({ data: [{ device_id: 'WTG-001' }] })
  await flush()
  assert.ok(harness.charts.every(chart => chart.disposed), '卸载后的异步回调不能遗留图表')
  assert.equal(harness.connected, false, '卸载后的异步回调不能重新连接')
  assert.equal(harness.resizeListeners.size, 0)
})
