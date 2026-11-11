const test = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const frontendRoot = path.resolve(__dirname, '..')
const stripModules = source => source
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\r?\n/gm, '')
  .replace(/^export /gm, '')
const plain = value => JSON.parse(JSON.stringify(value))

async function loadResearch(overrides = {}) {
  const { buildCompositeRequest } = await import('../src/utils/compositeResearch.js')
  const { formatErrorMessage } = await import('../src/utils/errorMessage.js')
  const noop = () => {}
  const context = {
    ref: value => ({ value }),
    computed: getter => ({ get value() { return getter() } }),
    watch: noop, onMounted: noop,
    useRoute: () => ({ query: {} }), useRouter: () => ({ push: noop }),
    ElMessage: { error: noop, warning: noop },
    buildCompositeRequest, formatErrorMessage,
    ...overrides,
  }
  const source = stripModules(readFileSync(path.join(frontendRoot, 'src/composables/useResearchDiagnosis.js'), 'utf8'))
    + '\nglobalThis.createResearch = useResearchDiagnosis;'
  vm.runInNewContext(source, context)
  const state = context.createResearch()
  state.selectedDeviceId.value = 'D1'
  state.selectedBatchIndex.value = 2
  state.selectedChannel.value = 3
  return state
}

test('Research全方法与复合流程使用独立请求，保留领域响应与CVS采集相位', async () => {
  const requests = []
  const domain = { evaluation_status: 'not_evaluable', diagnosis_conclusion: 'unknown', health_score: null,
    coverage: 'none', evaluations: [], deductions: [] }
  const state = await loadResearch({
    getChannelMethodAnalysis: async (...args) => { requests.push(['methods', ...args]); return { data: domain } },
    runCompositeResearch: async (...args) => { requests.push(['composite', ...args]); return { data: domain } },
  })
  state.runMode.value = 'all'
  await state.runAnalysis()
  assert.deepEqual(requests[0].slice(0, 5), ['methods', 'D1', 2, 3, 'all'])
  assert.equal(state.result.value, domain)
  const alignment = { carrier_phase_rad: [0, 1], planet_phase_rad: [0, 2], selected_planet: 0 }
  const composite = await loadResearchWithMetadata(requests, domain)
  composite.compositeAlignment.value = JSON.stringify(alignment)
  composite.rotFrequency.value = 2
  composite.denoise.value = 'vmd'
  await composite.runAnalysis()
  assert.deepEqual(plain(requests[1]), ['composite', 'D1', 2, 3, {
    method: 'composite_cvs_med_msb', options: {}, rot_freq_hz: 2, alignment,
  }])
  assert.equal(composite.result.value, domain)
  assert.equal(composite.loading.value, false)
})

async function loadResearchWithMetadata(requests, domain, errors = []) {
  const mounted = []
  const state = await loadResearch({
    onMounted: callback => mounted.push(callback),
    getAllDeviceData: async () => ({ data: [] }),
    getMethodInfo: async () => ({ data: { composite_cvs_med_msb: { category: 'composite' } } }),
    runCompositeResearch: async (...args) => { requests.push(['composite', ...args]); return { data: domain } },
    ElMessage: { error: message => errors.push(message), warning: message => errors.push(message) },
  })
  mounted.forEach(callback => callback())
  await new Promise(resolve => setImmediate(resolve))
  state.selectedMethod.value = 'composite_cvs_med_msb'
  return state
}

test('Research拒绝无效CVS记录并释放加载状态，不发送错误请求', async () => {
  const requests = [], errors = []
  const state = await loadResearchWithMetadata(requests, {}, errors)
  state.compositeAlignment.value = '{'
  await state.runAnalysis()
  assert.equal(requests.length, 0)
  assert.match(errors[0], /合法JSON/)
  assert.equal(state.result.value, null)
  assert.equal(state.loading.value, false)
})

test('诊断API封装仅发送当前领域接口接受的参数', async () => {
  const requests = []
  const context = { request: { get: async (...args) => { requests.push(args); return {} } } }
  const source = stripModules(readFileSync(path.join(frontendRoot, 'src/api/diagnosis.js'), 'utf8'))
    + '\nglobalThis.api = { getChannelDiagnosis, getChannelAnalyze };'
  vm.runInNewContext(source, context)
  await context.api.getChannelDiagnosis('D1', 2, 3, { denoise_method: 'vmd' })
  await context.api.getChannelDiagnosis('D1', 2, 3)
  await context.api.getChannelAnalyze('D1', 2, 3, {
    denoise: 'wavelet', rot_freq_hz: 25, strategy: 'old', bearing_method: 'old', gear_method: 'old', detrend: true,
  })
  assert.deepEqual(plain(requests), [
    ['/api/data/D1/2/3/diagnosis', { params: { denoise_method: 'vmd' } }],
    ['/api/data/D1/2/3/diagnosis', { params: {} }],
    ['/api/data/D1/2/3/analyze', { params: { denoise: 'wavelet', rot_freq_hz: 25 } }],
  ])
})
