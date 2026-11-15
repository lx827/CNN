const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { createRequire } = require('node:module')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')
const frontend = createRequire(path.resolve(__dirname, '../package.json'))
const vue = frontend('vue')

const source = readFileSync(path.resolve(__dirname, '../src/composables/useDataView.js'), 'utf8')
  .replace(/^import[\s\S]*?from ['"].*['"]\r?\n/gm, '')
  .replace(/^export const /gm, 'const ')
  .replace('export function useDataView()', 'globalThis.useDataView = function useDataView()')
const flush = async () => { await new Promise(resolve => setImmediate(resolve)); await vue.nextTick() }

function harness(overrides = {}) {
  const waveformRequests = [], reanalyzeRequests = []
  const device = {
    device_id: 'LOCAL', device_name: '本机采集', channel_count: 1,
    channel_names: { 4: '现场CH4' },
    batches: [
      { batch_index: 101, channel_count: 1, channels: [4], source_kind: 'dc24_counts' },
      { batch_index: 102, channel_count: 2, channels: [1, 4], source_kind: 'dc24_counts' },
    ],
  }
  const context = {
    ...vue, console,
    useRoute: () => ({ query: {} }), useRouter: () => ({ push() {} }),
    formatErrorMessage: error => String(error),
    getDiagnosisView: () => ({ label: '已诊断', scoreText: '90' }),
    getAllDeviceData: async () => ({ data: [device] }),
    getChannelData: async (...args) => {
      waveformRequests.push(args)
      return { data: { sample_rate: 1000, data: [0, 1] } }
    },
    getChannelDiagnosis: async () => { throw Object.assign(new Error('no cache'), { response: { status: 404 } }) },
    reanalyzeBatch: async (...args) => {
      reanalyzeRequests.push(args)
      return { data: { batch_index: 102, evaluation_status: 'evaluated', channels: {} } }
    },
    reanalyzeAllDevice: async () => ({ data: {} }),
    ElMessage: { success() {}, error() {}, warning() {}, info() {} },
    ElMessageBox: { confirm: async () => {} },
    bearingFrequencyAnnotations: () => [], significantBearingFaults: () => [], bearingMethodLabel: key => key,
    ...overrides,
  }
  for (const name of [
    'getChannelFFT', 'getChannelSTFT', 'getChannelEnvelope', 'getChannelGear',
    'getChannelStats', 'getChannelOrder', 'getChannelCepstrum', 'deleteBatch',
    'deleteSpecialBatches', 'exportChannelCSV', 'getChannelAnalyze',
    'getChannelFullAnalysis', 'updateBatchDiagnosis',
  ]) context[name] = async () => ({ data: {} })
  vm.runInNewContext(source, context, { filename: 'useDataView.js' })
  const renderer = vue.createRenderer({ createElement: () => ({ children: [] }), createText: text => ({ text }), createComment: () => ({}), insert: (c, p) => p.children.push(c), remove() {}, setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, patchProp() {} })
  const app = renderer.createApp({ setup: () => context.useDataView(), render: () => vue.h('div') })
  const instance = app.mount({ children: [] })
  return { app, state: instance.$.setupState, waveformRequests, reanalyzeRequests }
}

test('DataView按批次真实channels选择并请求仅存的CH4', async t => {
  const h = harness(); t.after(() => h.app.unmount()); await flush()
  h.state.selectBatch(
    { device_id: 'LOCAL', channel_count: 4, channel_names: {} },
    { batch_index: 101, channel_count: 1, channels: [4] },
  )
  await flush()
  assert.deepEqual(Array.from(h.state.channelOptions), [4])
  assert.equal(h.state.selectedChannel, 4)
  assert.equal(h.waveformRequests[0][2], 4)
})

test('DataView选段重诊发送样本范围与通道集合并切换到新批次', async t => {
  const h = harness(); t.after(() => h.app.unmount()); await flush()
  h.state.selectBatch(
    { device_id: 'LOCAL', channel_count: 4, channel_names: {} },
    { batch_index: 101, channel_count: 1, channels: [4], source_kind: 'dc24_counts' },
  )
  await flush()
  h.state.openReanalyzeDialog()
  Object.assign(h.state.reanalyzeForm, { mode: 'samples', start: 2, end: 6, channels: [1, 4] })
  await h.state.submitReanalyzeSelection()
  assert.deepEqual(JSON.parse(JSON.stringify(h.reanalyzeRequests[0])), [
    'LOCAL', 101, { start_sample: 2, end_sample: 6, channels: [1, 4] },
  ])
  assert.equal(h.state.selectedBatch.batch_index, 102)
  assert.deepEqual(Array.from(h.state.channelOptions), [1, 4])
})
