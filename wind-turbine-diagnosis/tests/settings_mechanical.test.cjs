// Bug25 回归:设置页机械参数卡片在配置加载完成前/失败时首渲染不得崩溃。
// 使用真实 Vue 运行时 + 真实 SFC 模板编译(el-* 按自定义元素处理,保留模板表达式求值路径),
// 复现原崩溃点:form.gear_teeth 初始为 {} 时模板直接访问 form.gear_teeth[String(i)].xxx。
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { createRequire } = require('node:module')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')

const frontendRequire = createRequire(path.resolve(__dirname, '../package.json'))
const vue = frontendRequire('vue')
const { parse, compileScript, compileTemplate } = frontendRequire('@vue/compiler-sfc')

// 剥离 import(含跨行大括号形式),源码以脚本形式在 vm 上下文中装载
const stripImports = (src) => src
  .replace(/^import\s*\{[\s\S]*?\}\s*from\s*['"][^'"]*['"];?[ \t]*\r?\n/gm, '')
  .replace(/^import\s+[^;\n]+;?[ \t]*\r?$/gm, '')

const planetary = stripImports(
  readFileSync(path.resolve(__dirname, '../src/utils/planetaryDiagnosis.js'), 'utf8')
).replace(/^export /gm, '')

const composable = stripImports(
  readFileSync(path.resolve(__dirname, '../src/composables/useSettings.js'), 'utf8')
).replace(/^export /gm, '')
  .replace(/^function useSettings/m, 'globalThis.useSettings = function useSettings')

const cardSource = readFileSync(path.resolve(__dirname, '../src/components/settings/MechanicalParamsCard.vue'), 'utf8')
const { descriptor } = parse(cardSource)
// import { a as b } from "vue" → var { a: b } = Vue(vm 上下文注入运行时)
const importFromVueToVar = () => (_, names) => `var {${names.replace(/\bas\b/g, ':')}} = Vue`

const cardScript = compileScript(descriptor, { id: 'mech-card-test' }).content
  .replace(/^import\s*\{([\s\S]*?)\}\s*from\s*["']vue["'];?[ \t]*\r?\n/m, importFromVueToVar())
  .replace('export default', 'globalThis.MechanicalParamsCard =')
// 真实编译模板:保留 v-for/属性访问等表达式。el-* 以透传插槽的桩组件全局注册:
// 桩必须调用 slots.default(),否则 tab 内容里的模板表达式不会求值,失去复现语义
// (与 element-plus el-tab-pane 默认非 lazy、全部渲染的行为一致)。
const cardTemplateCode = compileTemplate({
  source: descriptor.template.content,
  filename: 'MechanicalParamsCard.vue',
  id: 'mech-card-test',
}).code.replace(/^import\s*\{([\s\S]*?)\}\s*from\s*["']vue["'];?[ \t]*\r?\n/m, importFromVueToVar())
  .replace('export function render', 'function render')

const stubTags = [
  'el-alert', 'el-button', 'el-card', 'el-col', 'el-divider', 'el-form', 'el-form-item',
  'el-icon', 'el-input-number', 'el-option', 'el-row', 'el-select', 'el-tab-pane',
  'el-tabs', 'el-text', 'Check', 'CopyDocument',
]

const flush = async () => {
  await new Promise(resolve => setImmediate(resolve))
  await vue.nextTick()
}

function createHarness({ devicesPromise, configPromise, thresholdsPromise } = {}) {
  const created = []
  const renderer = vue.createRenderer({
    // 记录创建的元素标签,供断言模板实际渲染出的通道结构;
    // 节点维护父引用与按锚点插入,使 nextSibling/unmount 的 fragment 遍历可正常前进
    createElement: (tag) => { created.push(tag); return { tag, children: [] } },
    createText: (text) => ({ text }),
    createComment: () => ({}),
    insert: (child, parent, anchor) => {
      if (!parent) return
      child.__parent = parent
      const list = parent.children
      const idx = anchor ? list.indexOf(anchor) : -1
      if (idx === -1) list.push(child)
      else list.splice(idx, 0, child)
    },
    remove: (node) => {
      const list = node.__parent?.children
      if (list) { const idx = list.indexOf(node); if (idx !== -1) list.splice(idx, 1) }
    },
    setText: () => {},
    setElementText: () => {},
    parentNode: (node) => node.__parent || null,
    nextSibling: (node) => {
      const list = node.__parent?.children
      return list ? (list[list.indexOf(node) + 1] || null) : null
    },
    patchProp: () => {},
  })
  const context = {
    ...vue,
    Vue: vue,
    console,
    ElMessage: { success() {}, warning() {}, error() {} },
    getDevices: () => devicesPromise || new Promise(() => {}),          // 默认挂起:复现"配置未返回"的首渲染窗口
    getDeviceConfig: () => configPromise || new Promise(() => {}),
    getAlarmThresholds: () => thresholdsPromise || new Promise(() => {}),
    updateDeviceConfig: async () => { throw new Error('本测试不保存配置') },
    updateBatchDeviceConfig: async () => { throw new Error('本测试不保存配置') },
    updateAlarmThresholds: async () => { throw new Error('本测试不保存阈值') },
  }
  vm.runInNewContext(planetary, context, { filename: 'planetaryDiagnosis.js' })
  vm.runInNewContext(composable, context, { filename: 'useSettings.js' })
  vm.runInNewContext(cardScript, context, { filename: 'MechanicalParamsCard-script.js' })
  vm.runInNewContext(`${cardTemplateCode}\nglobalThis.MechanicalParamsCard.render = render`,
    context, { filename: 'MechanicalParamsCard-template.js' })

  // 每个 el-* 独立成桩,setup 阶段按注册名记录一次(实例计数,与渲染轮数无关);
  // 桩必须调用 slots.default(),否则 tab 内容里的模板表达式不会求值,失去复现语义
  // (与 element-plus el-tab-pane 默认非 lazy、全部渲染的行为一致)
  const makeStub = (tag) => ({
    name: `stub-${tag}`,
    setup(_, { slots }) {
      created.push(`#${tag}`)
      return () => (slots.default ? slots.default() : null)
    },
  })
  const stubs = Object.fromEntries(stubTags.map(tag => [tag, makeStub(tag)]))

  let settings = null
  let updateActiveChannel = null
  const host = {
    name: 'SettingsHost',
    setup() {
      settings = context.useSettings()
      // 稳定事件函数引用,避免每轮渲染因新函数 props 触发卡片整树重渲染
      updateActiveChannel = (value) => { settings.activeMechanicalChannel.value = value }
      return () => vue.h(context.MechanicalParamsCard, {
        form: settings.form.value,
        channelNames: settings.channelNames.value,
        savingMechanical: settings.savingMechanical.value,
        activeChannel: settings.activeMechanicalChannel.value,
        'onUpdate:activeChannel': updateActiveChannel,
      })
    },
  }
  return {
    created,
    get settings() { return settings },
    mount() {
      const app = renderer.createApp(host)
      for (const [tag, stub] of Object.entries(stubs)) app.component(tag, stub)
      app.mount({ children: [] })
      return { app }
    },
  }
}

// `#tag` 为桩组件实例记录(setup 每实例一次)
const countTag = (harness, tag) => harness.created.filter(item => item === `#${tag}`).length

test('配置未返回时首渲染不崩溃,且渲染出各通道机械参数表单', async t => {
  const harness = createHarness()
  const { app } = harness.mount()
  t.after(() => app.unmount())
  await flush()
  const form = harness.settings.form.value
  assert.equal(form.channel_count, 3)
  for (const ch of ['1', '2', '3']) {
    assert.ok(form.gear_teeth[ch], `gear_teeth[${ch}] 首渲染前应存在`)
    assert.ok('gear_type' in form.gear_teeth[ch], `gear_teeth[${ch}].gear_type 应存在`)
    assert.ok(form.bearing_params[ch] && 'n' in form.bearing_params[ch], `bearing_params[${ch}] 应为完整结构`)
  }
  assert.equal(countTag(harness, 'el-tab-pane'), 3, '应渲染 3 个通道页签')
  assert.ok(countTag(harness, 'el-select') >= 3, '每个通道应渲染齿轮结构选择')
  assert.ok(countTag(harness, 'el-input-number') >= 3, '每个通道应渲染轴承参数输入')
})

test('通道数调大时即时补齐新通道结构,重渲染不崩溃', async t => {
  const harness = createHarness()
  const { app } = harness.mount()
  t.after(() => app.unmount())
  await flush()
  harness.settings.form.value.channel_count = 8
  await flush()
  const form = harness.settings.form.value
  for (const ch of ['4', '5', '6', '7', '8']) {
    assert.ok(form.gear_teeth[ch] && 'gear_type' in form.gear_teeth[ch], `调大通道数后 gear_teeth[${ch}] 应被补齐`)
    assert.ok(form.bearing_params[ch] && 'n' in form.bearing_params[ch], `调大通道数后 bearing_params[${ch}] 应被补齐`)
  }
  assert.equal(countTag(harness, 'el-tab-pane'), 8, '重渲染应出现 8 个通道页签')
})

test('配置加载失败时仍保持完整通道结构,页面可渲染', async t => {
  const harness = createHarness({
    devicesPromise: Promise.resolve({ data: [] }),
    configPromise: Promise.reject(new Error('模拟配置接口失败')),
  })
  const { app } = harness.mount()
  t.after(() => app.unmount())
  await flush()
  await flush()
  const form = harness.settings.form.value
  for (const ch of ['1', '2', '3']) {
    assert.ok(form.gear_teeth[ch] && 'gear_type' in form.gear_teeth[ch], `加载失败后 gear_teeth[${ch}] 仍应完整`)
  }
  assert.equal(countTag(harness, 'el-tab-pane'), 3, '加载失败不影响通道页签渲染')
})
