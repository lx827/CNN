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
    status: 'evaluated',
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
  evaluation: { status: 'evaluated', indicators: {
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
  const context = composableContext({ ...utils, ...errors, ...overrides })
  vm.runInNewContext(source, context)
  return context.useDataView()
}

async function loadResearch(overrides = {}) {
  const utils = await bearingUtilsPromise
  const errors = await errorMessagePromise
  const { getDiagnosisStatusView } = await diagnosisStatusPromise
  const source = stripModules(readFileSync(path.join(frontendRoot, 'src/composables/useResearchDiagnosis.js'), 'utf8'))
    .replace('function useResearchDiagnosis()', 'globalThis.useResearchDiagnosis = function useResearchDiagnosis()')
    + '\nglobalThis.evaluationStatusText = evaluationStatusText; globalThis.evaluationStatusType = evaluationStatusType;'
    + '\nglobalThis.statusText = statusText; globalThis.statusType = statusType;'
  const context = composableContext({ ...utils, ...errors, getDiagnosisStatusView, ...overrides })
  vm.runInNewContext(source, context)
  return { state: context.useResearchDiagnosis(), context }
}

function selectBatch(state) {
  state.selectedDevice.value = { device_id: 'D1' }
  state.selectedBatch.value = { batch_index: 1 }
  state.selectedChannel.value = 1
}

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

test('研究页全方法/集成派生行区分轴承新契约与齿轮旧契约', async () => {
  const allData = {
    bearing_results: { envelope: envelopeResult(), sc_scoh: scScohResult() },
    gear_results: { gear_standard: gearResult() },
  }
  const { state, context } = await loadResearch({ getChannelMethodAnalysis: async () => ({ data: allData }) })
  state.selectedDeviceId.value = 'D1'
  state.selectedBatchIndex.value = 1
  state.selectedChannel.value = 1
  state.runMode.value = 'all'
  await state.runAnalysis()

  assert.deepEqual(state.allBearingRows.value[0].faults.map(item => item.fault_type), ['BPFO'])
  assert.match(state.allBearingRows.value[0].params, /频带2000Hz/)
  assert.deepEqual(state.allBearingRows.value[1].faults.map(item => item.fault_type), ['BPFI'])
  assert.deepEqual(plain(state.allGearRows.value[0].alerts), [{ indicator: 'ser', level: 'critical' }])
  const allNames = state.allBestIndicatorRows.value.map(item => item.name)
  assert.ok(allNames.includes('BPFO'))
  assert.ok(allNames.includes('BPFI'))
  assert.ok(allNames.includes('ser'))
  assert.equal(allNames.includes('OLD_BEARING'), false)

  state.result.value = { bearing: scScohResult(), gear: gearResult() }
  const bestRows = state.bestIndicatorRows.value
  assert.equal(bestRows.find(item => item.name === 'BPFI').value, 0.62)
  assert.equal(bestRows.find(item => item.source === '齿轮').state, '命中')
  assert.equal(context.evaluationStatusText('indeterminate'), '不可判定')
  assert.equal(context.evaluationStatusText('not_evaluable'), '不可评估')
  assert.equal(context.evaluationStatusType('indeterminate'), 'info')

  const limited = envelopeResult()
  limited.evaluation = {
    status: 'not_evaluable',
    indicators: {
      BPFO: { theory_hz: 300, evaluable: false, significant: null, snr: null, reason: 'out_of_band' },
    },
  }
  state.result.value = { bearing: limited, gear: gearResult() }
  const limitedRows = state.bestIndicatorRows.value
  assert.equal(limitedRows.find(item => item.name === 'BPFO').state, '不可评估')
  assert.equal(limitedRows.find(item => item.name === 'BPFO').type, 'info')
  assert.equal(limitedRows.find(item => item.source === '齿轮').state, '命中')
})

test('诊断状态 adapter 显式覆盖合法状态并对非法值中性兜底', async () => {
  const { getDiagnosisStatusView } = await diagnosisStatusPromise
  const cases = [
    ['normal', '正常', 'success', 'success'],
    ['warning', '预警', 'warning', 'warning'],
    ['fault', '故障', 'danger', 'error'],
    ['critical', '故障', 'danger', 'error'],
    ['indeterminate', '不可判定', 'info', 'info'],
    ['not_evaluable', '不可评估', 'info', 'info'],
  ]
  for (const [status, text, tagType, alertType] of cases) {
    assert.deepEqual(getDiagnosisStatusView(status), { text, tone: tagType, tagType, alertType })
  }
  for (const status of [undefined, null, '', 'unexpected_status', 'normal ', 0, {}, '__proto__']) {
    assert.deepEqual(getDiagnosisStatusView(status), {
      text: '未知', tone: 'info', tagType: 'info', alertType: 'info',
    })
  }
})

test('Research 实际消费者只使用统一诊断状态 view', async () => {
  const { context } = await loadResearch()
  const { getDiagnosisStatusView } = await diagnosisStatusPromise
  for (const status of [
    'normal', 'warning', 'fault', 'critical', 'indeterminate', 'not_evaluable',
    undefined, null, '', 'unexpected_status',
  ]) {
    const view = getDiagnosisStatusView(status)
    assert.equal(context.statusText(status), view.text)
    assert.equal(context.statusType(status), view.tagType)
  }
})

test('DiagnosisDetail 实际消费者只使用统一诊断状态 view', async () => {
  const utils = await bearingUtilsPromise
  const { getDiagnosisStatusView } = await diagnosisStatusPromise
  const setup = loadSfcSetup('src/components/DiagnosisDetail.vue', 'DiagnosisDetailStatus', {
    ...utils, getDiagnosisStatusView,
  })
  for (const status of [
    'normal', 'warning', 'fault', 'critical', 'indeterminate', 'not_evaluable',
    undefined, null, '', 'unexpected_status',
  ]) {
    const bindings = setup({ orderAnalysis: { engine_result: { status } } })
    assert.equal(bindings.statusView.value.text, getDiagnosisStatusView(status).text)
    assert.equal(bindings.statusView.value.tagType, getDiagnosisStatusView(status).tagType)
  }
})

test('ComprehensiveSection 实际消费者只使用统一诊断状态 view', async () => {
  const { getDiagnosisStatusView } = await diagnosisStatusPromise
  const setup = loadSfcSetup(
    'src/components/dataview/ComprehensiveSection.vue',
    'ComprehensiveSectionStatus',
    {
      bearingMethodLabel: value => value,
      bearingEntries: noop,
      getDiagnosisStatusView,
      _mergeModels: (props, models) => ({ ...props, ...models }),
      _useModel: (props, name) => ({ value: props[name] }),
    },
  )
  for (const status of [
    'normal', 'warning', 'fault', 'critical', 'indeterminate', 'not_evaluable',
    undefined, null, '', 'unexpected_status',
  ]) {
    const bindings = setup({ strategyAnalyzeData: { status }, fullAnalysisData: { status } })
    const expected = getDiagnosisStatusView(status)
    assert.deepEqual(plain(bindings.strategyStatusView.value), expected)
    assert.deepEqual(plain(bindings.fullAnalysisStatusView.value), expected)
    assert.equal(bindings.strategyStatusView.value.alertType, expected.alertType)
  }
  const { statusAlertTitle, statusAlertDescription } = setup({})
  assert.equal(statusAlertTitle(getDiagnosisStatusView('normal')), '✅ 未检出显著故障特征')
  assert.equal(statusAlertDescription(getDiagnosisStatusView('normal'), '', '正常说明'), '正常说明')
  assert.equal(statusAlertDescription(getDiagnosisStatusView('warning'), '', '正常说明'), '')
  const indeterminate = getDiagnosisStatusView('indeterminate')
  assert.equal(statusAlertTitle(indeterminate), '诊断不可判定')
  assert.match(statusAlertDescription(indeterminate, '', '正常说明'), /不能据此判断/)
})

function loadSfcSetup(relativePath, exportName, globals) {
  const filename = path.join(frontendRoot, relativePath)
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  const compiled = compileScript(descriptor, { id: exportName }).content
    .replace('export default', `globalThis.${exportName} =`)
  const source = stripModules(compiled)
  const context = { console, computed, ...globals }
  vm.runInNewContext(source, context)
  return (props) => context[exportName].setup(props, { expose: noop })
}

test('DiagnosisDetail 实际 setup 分别派生包络评估、SC/SCoh 与齿轮指标', async () => {
  const utils = await bearingUtilsPromise
  const setup = loadSfcSetup('src/components/DiagnosisDetail.vue', 'DiagnosisDetail', utils)
  const bindings = setup({
    orderAnalysis: {
      engine_result: {
        bearing: scScohResult(),
        gear: gearResult(),
      },
    },
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
    fmt: value => Number(value).toFixed(4),
    evaluationStatusType: status => status === 'evaluated' ? 'success' : 'info',
    evaluationStatusText: status => status === 'evaluated' ? '已评估' : '不可判定',
  })
  const result = scScohResult()
  const bindings = setup({ result, selectedMethodInfo: { category: 'bearing' }, filterPlanetaryResult: {} })

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
