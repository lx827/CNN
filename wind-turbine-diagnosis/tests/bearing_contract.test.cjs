// 轴承新响应契约回归：频谱图、标注、研究页汇总与诊断明细。
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { createRequire } = require('node:module')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const test = require('node:test')
const vm = require('node:vm')

const frontendRoot = path.resolve(__dirname, '..')
const requireFrontend = createRequire(path.join(frontendRoot, 'package.json'))
const { parse, compileScript } = requireFrontend('@vue/compiler-sfc')
const bearingUtilsPromise = import(pathToFileURL(path.join(frontendRoot, 'src/utils/bearingDiagnosis.js')).href)
const compositeUtilsPromise = import(pathToFileURL(path.join(frontendRoot, 'src/utils/compositeResearch.js')).href)
const researchDisplayPromise = import(pathToFileURL(path.join(frontendRoot, 'src/utils/researchDisplay.js')).href)
const diagnosisStatusPromise = import(pathToFileURL(path.join(frontendRoot, 'src/utils/diagnosisStatus.js')).href)
const errorMessagePromise = import(pathToFileURL(path.join(frontendRoot, 'src/utils/errorMessage.js')).href)

const stripModules = source => source
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\r?\n/gm, '')
  .replace(/^export /gm, '')

const ref = value => ({ value })
const computed = getter => ({ get value() { return getter() } })
const noop = () => {}
const asyncNoop = async () => ({ data: null })
const plain = value => JSON.parse(JSON.stringify(value))

const envelopeResult = () => ({
  method: 'envelope',
  spectrum: {
    frequency_hz: [0, 50, 100, 150],
    amplitude: [0.1, 0.4, 2.5, 0.2],
    amplitude_unit: 'g',
    scaling: 'single_sided_amplitude',
  },
  band: { low_hz: 1800, high_hz: 2200, center_hz: 2000, width_hz: 400 },
  features: { spectral_power_proxy: 6.5, BPFO_env_ratio: 0.25 },
  evaluation: {
    evaluation_status: 'evaluated',
    indicators: {
      BPFO: { theory_hz: 100, detected_hz: 100, snr: 8.25, significant: true },
      envelope_peak_snr_stat: { value: 3.2, snr: 3.2, significant: false },
    },
  },
  // 迁移期若混入旧字段，也绝不能覆盖新 evaluation。
  fault_indicators: { OLD_BEARING: { theory_hz: 50, significant: true, snr: 99 } },
})

const scScohResult = () => ({
  method: 'sc_scoh',
  evaluation_kind: 'sc_scoh',
  spectrum: null,
  band: null,
  features: { spectral_power_proxy: 0 },
  evaluation: { evaluation_status: 'evaluated', indicators: {
    BPFI: { theory_cyclic_frequency_hz: 90, scoh_peak: 0.62, coherence_background_ratio: 6.4, significant: true, evaluable: true },
  } },
})

const gearResult = () => ({
  ser: 4.2,
  fault_indicators: { ser: { value: 4.2, critical: true, warning: true } },
})

function composableContext(extra = {}) {
  return {
    console,
    ref,
    computed,
    watch: noop,
    onMounted: noop,
    onUnmounted: noop,
    nextTick: async () => {},
    useRoute: () => ({ query: {} }),
    useRouter: () => ({ push: noop }),
    ElMessage: { error: noop, success: noop, warning: noop, info: noop },
    ElMessageBox: { confirm: async () => {} },
    getAllDeviceData: asyncNoop,
    getChannelData: asyncNoop,
    getChannelFFT: asyncNoop,
    getChannelSTFT: asyncNoop,
    getChannelEnvelope: asyncNoop,
    getChannelGear: asyncNoop,
    getChannelStats: asyncNoop,
    getChannelOrder: asyncNoop,
    getChannelCepstrum: asyncNoop,
    deleteBatch: asyncNoop,
    deleteSpecialBatches: asyncNoop,
    exportChannelCSV: noop,
    getChannelAnalyze: asyncNoop,
    getChannelFullAnalysis: asyncNoop,
    getChannelDiagnosis: asyncNoop,
    updateBatchDiagnosis: asyncNoop,
    reanalyzeBatch: asyncNoop,
    reanalyzeAllDevice: asyncNoop,
    getMethodInfo: asyncNoop,
    getChannelMethodAnalysis: asyncNoop,
    getChannelResearchAnalysis: asyncNoop,
    ...extra,
  }
}

async function loadDataView(overrides = {}) {
  const utils = await bearingUtilsPromise
  const errors = await errorMessagePromise
  const source = stripModules(readFileSync(path.join(frontendRoot, 'src/composables/useDataView.js'), 'utf8'))
    .replace('function useDataView()', 'globalThis.useDataView = function useDataView()')
  const domainViews = await diagnosisStatusPromise
  const context = composableContext({ ...utils, ...errors, ...domainViews, ...overrides })
  vm.runInNewContext(source, context)
  return context.useDataView()
}

async function loadResearch(overrides = {}) {
  const utils = await bearingUtilsPromise
  const errors = await errorMessagePromise
  const { getDiagnosisView } = await diagnosisStatusPromise
  const compositeUtils = await compositeUtilsPromise
  const source = stripModules(readFileSync(path.join(frontendRoot, 'src/composables/useResearchDiagnosis.js'), 'utf8'))
    .replace('function useResearchDiagnosis()', 'globalThis.useResearchDiagnosis = function useResearchDiagnosis()')
  const context = composableContext({ ...utils, ...errors, ...compositeUtils, getDiagnosisView, runCompositeResearch: asyncNoop, ...overrides })
  vm.runInNewContext(source, context)
  return { state: context.useResearchDiagnosis(), context }
}

function selectBatch(state) {
  state.selectedDevice.value = { device_id: 'D1' }
  state.selectedBatch.value = { batch_index: 1 }
  state.selectedChannel.value = 1
}

test('明细查询使用当前通道去噪组合，重新诊断保留unknown/null与独立通道结果', async () => {
  const requests = [], messages = []
  const channel = { evaluation_status: 'not_evaluable', diagnosis_conclusion: 'unknown', health_score: null }
  const state = await loadDataView({
    getChannelDiagnosis: async (...args) => { requests.push(args); return { data: channel } },
    reanalyzeBatch: async () => ({ data: { ...channel, channels: { ch2: channel } } }),
    ElMessage: { success: message => messages.push(message), warning: noop, error: noop },
  })
  selectBatch(state)
  state.selectedChannel.value = 2
  state.denoiseMethod.value = 'wavelet'
  await state.loadDiagnosisDetail()
  assert.deepEqual(plain(requests[0]), ['D1', 1, 2, { denoise_method: 'wavelet' }])
  assert.equal(state.diagnosisDetailData.value.health_score, null)
  await state.onReanalyze()
  assert.equal(state.selectedBatch.value.diagnosis_conclusion, 'unknown')
  assert.equal(state.selectedBatch.value.health_score, null)
  assert.equal(state.diagnosisDetailData.value, channel)
  assert.doesNotMatch(messages[0], /null|100|0 分/)
  assert.match(messages[0], /不可评估/)
})

test('DataView和研究页实际失败分支显示422方法及原因', async () => {
  const messages = []
  const reject = async () => { throw { response: { data: { detail: {
    status: 'not_evaluable', method: 'vmd', reason: 'maximum_iterations_reached',
  } } } } }
  const extra = { ElMessage: { error: message => messages.push(message), warning: noop, success: noop, info: noop } }
  const view = await loadDataView({ ...extra, getChannelEnvelope: reject })
  selectBatch(view)
  await view.computeEnvelope()
  assert.match(messages[0], /vmd.*maximum_iterations_reached/)
  assert.equal(view.computedEnvelope.value, false)
  const { state } = await loadResearch({ ...extra, getChannelMethodAnalysis: reject })
  state.selectedDeviceId.value = 'D1'
  state.selectedBatchIndex.value = 1
  state.selectedChannel.value = 1
  await state.runAnalysis()
  assert.match(messages[1], /vmd.*maximum_iterations_reached/)
  assert.equal(messages.some(message => message.includes('[object Object]')), false)
})

test('DataView 包络图读取结构化 spectrum，并从 evaluation 生成标注', async () => {
  const state = await loadDataView({ getChannelEnvelope: async () => ({ data: envelopeResult() }) })
  selectBatch(state)
  await state.computeEnvelope()

  const option = state.envelopeOption.value
  assert.deepEqual(Array.from(option.xAxis.data), [0, 50, 100, 150])
  assert.deepEqual(Array.from(option.series[0].data), [0.1, 0.4, 2.5, 0.2])
  assert.match(option.yAxis.name, /g/)
  assert.match(option.yAxis.name, /single_sided_amplitude/)
  const bpfoLine = option.series[0].markLine.data.find(line => line.name.includes('BPFO'))
  assert.equal(bpfoLine.xAxis, 2)
  assert.equal(bpfoLine.lineStyle.color, '#F5222D')
  assert.equal(state.faultFreqAnnotations.value.some(item => item.name === 'OLD_BEARING'), false)
})

test('SC/SCoh 无包络谱时保留专属指标标注，不构造空图表', async () => {
  const state = await loadDataView({ getChannelEnvelope: async () => ({ data: scScohResult() }) })
  selectBatch(state)
  await state.computeEnvelope()

  assert.equal(state.computedEnvelope.value, true)
  assert.equal(state.envelopeOption.value, null)
  assert.deepEqual(plain(state.faultFreqAnnotations.value.map(item => ({
    name: item.name, freq: item.freq, type: item.type, detected: item.detected,
  }))), [{ name: 'BPFI', freq: 90, type: 'bearing_sc_scoh', detected: true }])
})

test('DataView 轴承汇总使用新指标，齿轮汇总继续使用旧 fault_indicators', async () => {
  const state = await loadDataView()
  state.fullAnalysisData.value = {
    bearing_results: { envelope: envelopeResult(), sc_scoh: scScohResult() },
    gear_results: { standard: gearResult() },
  }

  const bearingRows = state.bearingSummaryTable.value
  assert.deepEqual(bearingRows[0].faults.map(item => item.fault_type), ['BPFO'])
  assert.equal(bearingRows[0].params.includes('1800~2200Hz'), true)
  assert.deepEqual(bearingRows[1].faults.map(item => item.fault_type), ['BPFI'])
  assert.equal(bearingRows[1].faults[0].coherence_background_ratio, 6.4)
  assert.equal(bearingRows[1].evaluationStatus, 'evaluated')
  assert.equal(bearingRows.flatMap(row => row.faults).some(item => item.fault_type === 'OLD_BEARING'), false)
  assert.deepEqual(plain(state.gearSummaryTable.value[0].alerts), [{ indicator: 'ser', level: 'critical' }])
})

test('策略诊断同时保留轴承 evaluation 标注和齿轮旧字段标注', async () => {
  const response = {
    bearing: envelopeResult(),
    gear: { fault_indicators: { mesh: { frequency_hz: 125, critical: true } } },
    rot_freq_hz: 25,
  }
  const state = await loadDataView({ getChannelAnalyze: async () => ({ data: response }) })
  selectBatch(state)
  await state.computeStrategyAnalyze()

  const annotations = state.faultFreqAnnotations.value
  assert.equal(annotations.find(item => item.name === 'BPFO').type, 'bearing')
  assert.equal(annotations.find(item => item.name === 'mesh').type, 'gear')
  assert.equal(annotations.find(item => item.name === 'mesh').freq, 125)
  assert.equal(annotations.some(item => item.name === 'OLD_BEARING'), false)
})

function loadSfcSetup(relativePath, exportName, globals) {
  const filename = path.join(frontendRoot, relativePath)
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  const compiled = compileScript(descriptor, { id: exportName }).content
    .replace('export default', `globalThis.${exportName} =`)
  const source = stripModules(compiled)
  // 子组件模板由独立契约覆盖；SFC setup 仍需持有真实导入对应的绑定名。
  const context = { console, computed, PlanetaryResult: {}, DiagnosisCoverage: {}, CompositeResult: {}, ...globals }
  vm.runInNewContext(source, context)
  return (props) => context[exportName].setup(props, { expose: noop })
}

test('DiagnosisDetail 实际 setup 分别派生包络评估、SC/SCoh 与齿轮指标', async () => {
  const utils = await bearingUtilsPromise
  const setup = loadSfcSetup('src/components/DiagnosisDetail.vue', 'DiagnosisDetail', { ...utils, ...await diagnosisStatusPromise })
  const bindings = setup({
    diagnosis: { bearing: scScohResult(), gear: gearResult() },
    rotFreq: 25,
    rotRpm: 1500,
  })

  assert.deepEqual(plain(bindings.bearingIndicators.value), [])
  assert.deepEqual(plain(bindings.bearingFreqItems.value), [])
  assert.equal(bindings.scScohItems.value[0].value, 0.62)
  assert.equal(bindings.scScohItems.value[0].coherenceRatio, 6.4)
  assert.deepEqual(plain(bindings.gearIndicators.value.map(item => item.key)), ['ser'])
  assert.equal(bindings.bearingIndicators.value.some(item => item.key === 'OLD_BEARING'), false)
})

test('SingleResultPanels 实际 setup 分离 evaluation 与 SC/SCoh 条目', async () => {
  const utils = await bearingUtilsPromise
  const setup = loadSfcSetup('src/components/research/SingleResultPanels.vue', 'SingleResultPanels', {
    ...utils,
    ...await researchDisplayPromise,
    fmt: value => Number(value).toFixed(4),
    evaluationStatusType: status => status === 'evaluated' ? 'success' : 'info',
    evaluationStatusText: status => status === 'evaluated' ? '已评估' : '不可判定',
  })
  const result = scScohResult()
  const bindings = setup({ result, selectedMethodInfo: { category: 'bearing' } })

  assert.deepEqual(plain(bindings.bearingEvaluationItems.value), [])
  assert.deepEqual(plain(bindings.scScohItems.value.map(item => item.name)), ['BPFI'])
  assert.equal(bindings.scScohItems.value[0].info.scoh_peak, 0.62)
})

test('研究页将显式MCKD目标、CPW稳定性和已知转频传给实际请求', async () => {
  const requests = []
  const { state } = await loadResearch({
    getChannelMethodAnalysis: async (...args) => { requests.push(args); return { data: scScohResult() } },
    getChannelResearchAnalysis: async (...args) => { requests.push(args); return { data: {} } },
  })
  state.selectedDeviceId.value = 'D1'
  state.selectedBatchIndex.value = 1
  state.selectedChannel.value = 1
  state.selectedMethod.value = 'mckd'
  state.targetFault.value = 'BPFI'
  state.combFrequencies.value = '25, 50'
  state.combIsStable.value = true
  state.rotFrequency.value = 25
  await state.runAnalysis()
  assert.equal(requests[0][3], 'mckd')
  assert.deepEqual(plain(requests[0][4]), {
    denoise: 'none', target_fault: 'BPFI', comb_frequencies_hz: [25, 50], comb_is_stable: true, rot_freq_hz: 25,
  })
  state.runMode.value = 'ensemble'
  await state.runAnalysis()
  assert.equal(requests[1][3].target_fault, 'BPFI')
  assert.equal(requests[1][3].comb_is_stable, true)
  state.combFrequencies.value = 'invalid'
  await state.runAnalysis()
  assert.equal(requests.length, 2)
})

test('诊断API封装传递方法前提并以重复查询键序列化多梳状频率', async () => {
  const requests = []
  const source = stripModules(readFileSync(path.join(frontendRoot, 'src/api/diagnosis.js'), 'utf8'))
    + '\nglobalThis.methods = { getChannelMethodAnalysis, getChannelResearchAnalysis };'
  const context = { request: { get: async (...args) => { requests.push(args); return { data: {} } } } }
  vm.runInNewContext(source, context)
  const config = { target_fault: 'BPFI', rot_freq_hz: 25, comb_frequencies_hz: [25, 50], comb_is_stable: true }
  await context.methods.getChannelMethodAnalysis('D1', 1, 1, 'mckd', config)
  await context.methods.getChannelResearchAnalysis('D1', 1, 1, config)
  for (const [, options] of requests) {
    assert.equal(options.params.target_fault, 'BPFI')
    assert.equal(options.params.rot_freq_hz, 25)
    assert.deepEqual(plain(options.params.comb_frequencies_hz), [25, 50])
    assert.equal(options.params.comb_is_stable, true)
    assert.equal(options.paramsSerializer.indexes, null)
  }
})
