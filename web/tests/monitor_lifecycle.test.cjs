// 使用真实 Vue 生命周期运行 Monitor，替换网络与图表以隔离云端数据。
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { createRequire } = require('node:module')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')
let getDiagnosisView, formatErrorMessage, chartTheme, constants
test.before(async () => {
  ({ getDiagnosisView } = await import('../src/utils/diagnosisStatus.js'))
  chartTheme = await import('../src/utils/chartTheme.js')
  ;({ formatErrorMessage } = await import('../src/utils/errorMessage.js'))
  constants = await import('../src/utils/constants.js')
})

const frontendRequire = createRequire(path.resolve(__dirname, '../package.json'))
const vue = frontendRequire('vue')
const { parse, compileScript } = frontendRequire('@vue/compiler-sfc')
const source = readFileSync(path.resolve(__dirname, '../src/views/Monitor.vue'), 'utf8')
const { descriptor } = parse(source)
const script = compileScript(descriptor, { id: 'monitor-lifecycle-test' }).content
  .replace(/^import .* from ['"].*['"]\r?\n/gm, '')
  .replace('export default', 'globalThis.Monitor =')
// 视图逻辑抽至 composables/useMonitor.js,测试在同一上下文装载其源码
const composable = readFileSync(path.resolve(__dirname, '../src/composables/useMonitor.js'), 'utf8')
  .replace(/^import .*\r?\n/gm, '')
  .replace(/^export /gm, '')
  .replace(/^function useMonitor/m, 'globalThis.useMonitor = function useMonitor')

const acquisitionApi = readFileSync(path.resolve(__dirname, '../src/api/acquisition.js'), 'utf8')
  .replace(/^import .*\r?\n/gm, '')
  .replace(/^export const (\w+) = /gm, 'globalThis.$1 = ')

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

const activeAgent = {
  id: 'dc24-pi', source: 'dc24_tcp', online: true,
  state: { version: 3, sample_rates: [50, 5000, 10000], save_directory: '/device/records' }
}
const activeDevice = { device_id: 'dc24-pi', name: '实机', sample_rate: 10000, window_seconds: 10 }

function createHarness({ devicesPromise, fetchData, getAgents = async () => [], createRecording, jobStatus, timers = {} } = {}) {
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
    console, getDiagnosisView, formatErrorMessage, ...chartTheme, ...constants,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    ...timers,
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
    getRealtimeVibrationData: async (...args) => {
      requests++
      if (fetchData) return fetchData(...args)
      return { data: { channels, sensorParams: { estimated_rpm: 1200 } } }
    },
    request: {
      async post(url, body) {
        assert.equal(url, '/api/acquisition/remote-recordings')
        return { data: await createRecording(body) }
      },
      async get(url) {
        if (url === '/api/acquisition/agents') return { data: await getAgents() }
        assert.equal(url, '/api/acquisition/jobs/remote-job')
        return { data: await jobStatus() }
      }
    },
    requestCollection: async device => { throw new Error(`错误地调用旧采集入口：${device}`) },
    getWebSocketClient: () => socket,
    ElMessage: { success() {}, warning() {}, error() {} },
    // 视图拆分后 __returned__ 引用子组件标识符(import 已剥离),提供空壳桩
    SensorStatusCard: {}, RunParamsCard: {}, CollectionProgress: {}
  }
  vm.runInNewContext(acquisitionApi, context, { filename: 'acquisition.js' })
  vm.runInNewContext(composable, context, { filename: 'useMonitor.js' })
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

test('监测诊断使用服务端两维结论，RMS不能替代未知评估', async t => {
  const received = channels.map((channel, index) => ({ ...channel,
    rms: index === 0 ? 999 : 0,
    evaluation_status: index === 0 ? 'evaluated' : 'not_evaluable',
    diagnosis_conclusion: index === 0 ? 'normal' : 'unknown',
    health_score: index === 0 ? 98 : null,
  }))
  const harness = createHarness({ fetchData: async () => ({ data: { channels: received, sensorParams: {} } }) })
  const { app, state } = harness.mount()
  t.after(() => app.unmount())
  await flush()
  assert.equal(state.sensors[0].status, 'success')
  assert.equal(state.sensors[0].statusText, '正常')
  assert.equal(state.sensors[1].status, 'info')
  assert.equal(state.sensors[1].statusText, '不可评估')
})

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
    await new Promise(resolve => setTimeout(resolve, 130))
    await flush()
    assert.equal(harness.requests, before + 1, '返回页面后一次推送只触发一次请求')
  } finally {
    second.app.unmount()
  }
})

test('其他设备的推送不刷新，连续推送只产生一次请求', async t => {
  const harness = createHarness()
  const page = harness.mount()
  t.after(() => page.app.unmount())
  await flush()
  const before = harness.requests
  for (const callback of harness.listeners.get('sensor_update')) callback({ device_id: 'OTHER' })
  await new Promise(resolve => setTimeout(resolve, 130))
  assert.equal(harness.requests, before)
  for (const event of ['sensor_update', 'diagnosis_update', 'sensor_update']) {
    for (const callback of harness.listeners.get(event)) callback({ device_id: 'WTG-001' })
  }
  await new Promise(resolve => setTimeout(resolve, 130))
  assert.equal(harness.requests, before + 1)
})

test('切换设备时慢请求不能覆盖新设备，推送到达时保留一次后续刷新', async t => {
  const pending = []
  const harness = createHarness({ fetchData: (deviceId, preferSpecial) => new Promise(resolve => {
    pending.push({ deviceId, preferSpecial, resolve })
  }) })
  const page = harness.mount()
  t.after(() => page.app.unmount())
  await flush()
  assert.equal(pending.length, 1)
  page.state.selectedMonitorDevice = 'WTG-002'
  page.state.onMonitorDeviceChange()
  await flush()
  // 在途请求串行，旧响应结束后必须刷新当前设备。
  pending[0].resolve({ data: { channels, sensorParams: { device: 'OLD' } } })
  await flush()
  assert.notEqual(page.state.params.device, 'OLD')
  assert.equal(pending.length, 2)
  assert.equal(pending[1].deviceId, 'WTG-002')
  pending[1].resolve({ data: { channels: [channels[1]], sensorParams: { device: 'NEW' } } })
  await flush()
  assert.equal(page.state.params.device, 'NEW')
  assert.equal(page.state.activeChannel, 0)
})

test('请求进行中收到新推送会在结束后刷新，卸载会取消待刷新', async t => {
  let resolveRequest
  let calls = 0
  const harness = createHarness({ fetchData: () => {
    calls++
    if (calls === 2) return new Promise(resolve => { resolveRequest = resolve })
    return Promise.resolve({ data: { channels, sensorParams: {} } })
  } })
  const page = harness.mount()
  t.after(() => page.app.unmount())
  await flush()
  const emit = () => {
    for (const callback of harness.listeners.get('sensor_update')) callback({ device_id: 'WTG-001' })
  }
  emit()
  await new Promise(resolve => setTimeout(resolve, 130))
  assert.equal(calls, 2)
  emit()
  await new Promise(resolve => setTimeout(resolve, 130))
  resolveRequest({ data: { channels, sensorParams: {} } })
  await flush()
  assert.equal(calls, 3, '在途请求不能吞掉后续推送')
  emit()
  page.app.unmount()
  await new Promise(resolve => setTimeout(resolve, 130))
  assert.equal(calls, 3)
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

test('真实边端按上报档位提交远程采集，按 job 状态更新并加载采集批次', async t => {
  const requests = []
  const timers = new Map()
  let timerId = 0, resolveStatus, calls = 0
  const job = { id: 'remote-job', agent_id: 'dc24-pi', sample_rate: 10000, duration: 10, status: 'pending' }
  const harness = createHarness({
    devicesPromise: Promise.resolve({ data: [{ device_id: 'WTG-001' }, activeDevice] }),
    getAgents: async () => [
      { ...activeAgent, id: 'replay-agent', source: 'recording_replay' },
      { ...activeAgent, id: 'other-hardware' },
      activeAgent,
    ],
    fetchData: async (device, preferSpecial) => {
      requests.push([device, preferSpecial])
      return { data: { channels, sensorParams: {} } }
    },
    createRecording: body => {
      assert.deepEqual({ ...body }, { agent_id: 'dc24-pi', sample_rate: 10000, duration: 10 })
      return job
    },
    jobStatus: () => { calls++; return new Promise(resolve => { resolveStatus = resolve }) },
    timers: {
      setTimeout: callback => { timers.set(++timerId, callback); return timerId },
      clearTimeout: id => timers.delete(id)
    },
  })
  const { app, state } = harness.mount()
  t.after(() => app.unmount())
  await flush()
  assert.deepEqual(Array.from(state.collectAgents, agent => agent.id), ['other-hardware', 'dc24-pi'])
  state.selectedCollectDevice = 'dc24-pi'
  await vue.nextTick()
  await state.requestCollect()
  const poll = () => {
    assert.equal(timers.size, 1)
    const [id, callback] = [...timers.entries()][0]
    timers.delete(id)
    callback()
  }
  assert.match(state.collectionStatus, /等待边端/)
  poll()
  assert.equal(calls, 1)
  assert.equal(timers.size, 0, '上次查询未返回时不能预约下一轮查询')
  resolveStatus({ ...job, status: 'capturing', progress: { samples_per_channel: 50000 } })
  await flush()
  assert.match(state.collectionStatus, /采集/)
  assert.equal(state.collectionProgress, 50)
  poll()
  resolveStatus({ ...job, status: 'uploading' })
  await flush()
  assert.match(state.collectionStatus, /上传/)
  poll()
  resolveStatus({ ...job, status: 'completed', metadata: { diagnosis_device_id: 'dc24-pi' } })
  await flush()
  assert.equal(state.isCollecting, false)
  assert.match(state.collectionStatus, /已完成/)
  assert.deepEqual(requests.at(-1), ['dc24-pi', true])
  assert.equal(timers.size, 0)
})

test('禁止回放和未选档位的采集请求，卸载后停止任务状态查询', async () => {
  const timers = new Map()
  let timerId = 0, resolveStatus, calls = 0, creations = 0
  const job = { id: 'remote-job', agent_id: 'dc24-pi', sample_rate: 10000, duration: 10, status: 'pending' }
  const harness = createHarness({
    devicesPromise: Promise.resolve({ data: [{ ...activeDevice, sample_rate: 25600 }] }),
    getAgents: async () => [activeAgent, { ...activeAgent, id: 'dc24-replay', source: 'recording_replay' }],
    createRecording: () => { creations++; return job },
    jobStatus: () => { calls++; return new Promise(resolve => { resolveStatus = resolve }) },
    timers: {
      setTimeout: callback => { timers.set(++timerId, callback); return timerId },
      clearTimeout: id => timers.delete(id),
    },
  })
  const { app, state } = harness.mount()
  await flush()
  state.selectedCollectDevice = 'dc24-replay'
  await state.requestCollect()
  assert.equal(creations, 0)
  state.selectedCollectDevice = 'dc24-pi'
  await vue.nextTick()
  await state.requestCollect()
  assert.equal(creations, 0, '设备设置不在边端档位时不得静默选择')
  state.selectedSampleRate = 10000
  await state.requestCollect()
  assert.equal(creations, 1)
  const [id, callback] = [...timers.entries()][0]
  timers.delete(id)
  callback()
  assert.equal(calls, 1)
  app.unmount()
  resolveStatus(job)
  await flush()
  assert.equal(timers.size, 0)
})
