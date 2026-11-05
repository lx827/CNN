const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const test = require('node:test')
const { createRequire } = require('node:module')
const front = createRequire(path.resolve(__dirname, '../../wind-turbine-diagnosis/package.json'))
const vue = front('vue'), { parse, compileScript } = front('@vue/compiler-sfc')

test('一键入口首次登录后返回采集页，正常登录仍返回总览', async () => {
  let guard
  const routerSource = readFileSync(path.resolve(__dirname, '../../wind-turbine-diagnosis/src/router/index.js'), 'utf8')
    .replace(/^import .*\r?\n/gm, '').replace('export default router', '')
  vm.runInNewContext(routerSource, { Layout: {}, createWebHashHistory: () => ({}),
    createRouter: () => ({ beforeEach: fn => { guard = fn } }), localStorage: { getItem: () => null } })
  let next
  guard({ meta: {}, fullPath: '/acquisition' }, {}, value => { next = value })
  assert.equal(next.path, '/login'); assert.equal(next.query.redirect, '/acquisition')
  const { descriptor } = parse(readFileSync(path.resolve(__dirname, '../../wind-turbine-diagnosis/src/views/Login.vue'), 'utf8'))
  const script = compileScript(descriptor, { id: 'login-return' }).content
    .replace(/^import .* from ['"].*['"]\r?\n/gm, '').replace('export default', 'globalThis.Component =')
  const renderer = vue.createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), insert() {}, remove() {}, setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, patchProp() {} })
  for (const target of ['/acquisition', undefined, '//other.example']) {
    let pushed
    const context = { ...vue, useRouter: () => ({ push: x => { pushed = x } }), useRoute: () => ({ query: { redirect: target } }),
      localStorage: { setItem() {} }, ElMessage: { success() {}, error() {} }, login: async () => ({ access_token: 'fake-local-test-token' }) }
    vm.runInNewContext(script, context)
    context.Component.render = function () { vue.getCurrentInstance().setupState.formRef = { validate: async () => true }; return vue.h('div') }
    const app = renderer.createApp(context.Component), instance = app.mount({})
    await instance.$.setupState.handleLogin()
    assert.equal(pushed, target === '/acquisition' ? '/acquisition' : '/dashboard')
    app.unmount()
  }
})
