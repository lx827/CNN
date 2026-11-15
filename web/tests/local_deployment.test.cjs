const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')

const sourcePath = (...parts) => path.resolve(__dirname, '../src', ...parts)
const stripImports = source => source.replace(/^import .*\r?\n/gm, '')

function routerGuard(local) {
  let guard
  const source = stripImports(fs.readFileSync(sourcePath('router/index.js'), 'utf8'))
    .replace('export default router', '')
  vm.runInNewContext(source, {
    Layout: {},
    createWebHashHistory: () => ({}),
    createRouter: () => ({ beforeEach: fn => { guard = fn } }),
    isLocalDeployment: () => local,
    localStorage: { getItem: () => null }
  })
  return guard
}

function requestHarness(local) {
  const interceptors = {}
  const removed = []
  const source = stripImports(fs.readFileSync(sourcePath('utils/request.js'), 'utf8'))
    .replace('export default request', 'globalThis.request = request')
  const context = {
    axios: { create: () => ({ interceptors: {
      request: { use: fn => { interceptors.request = fn } },
      response: { use: (onFulfilled, onRejected) => { interceptors.response = onRejected } }
    } }) },
    ElMessage: { error() {} },
    getApiBaseURL: () => '/',
    formatErrorMessage: () => 'error',
    isLocalDeployment: () => local,
    localStorage: { getItem: () => 'stale-token', removeItem: key => removed.push(key) },
    window: { location: { hash: '#/acquisition' } },
    Promise, Error
  }
  vm.runInNewContext(source, context)
  return { interceptors, removed, context }
}

test('本地部署路由无需 token，云端仍跳转登录页', () => {
  let localNext = 'not-called'
  routerGuard(true)({ meta: {}, fullPath: '/acquisition' }, {}, value => { localNext = value })
  assert.equal(localNext, undefined)
  let cloudNext
  routerGuard(false)({ meta: {}, fullPath: '/acquisition' }, {}, value => { cloudNext = value })
  assert.equal(cloudNext.path, '/login')
  assert.equal(cloudNext.query.redirect, '/acquisition')
})

test('本地请求不携带旧 token，云端请求保持 Bearer 认证', () => {
  const localConfig = { headers: {} }
  requestHarness(true).interceptors.request(localConfig)
  assert.equal(localConfig.headers.Authorization, undefined)
  const cloudConfig = { headers: {} }
  requestHarness(false).interceptors.request(cloudConfig)
  assert.equal(cloudConfig.headers.Authorization, 'Bearer stale-token')
})

test('本地 401 不清 token 或跳登录，云端 401 保持现有处理', async () => {
  const local = requestHarness(true)
  await local.interceptors.response({ response: { status: 401 }, config: {} }).catch(() => {})
  assert.deepEqual(local.removed, [])
  assert.equal(local.context.window.location.hash, '#/acquisition')
  const cloud = requestHarness(false)
  await cloud.interceptors.response({ response: { status: 401 }, config: {} }).catch(() => {})
  assert.deepEqual(cloud.removed, ['access_token'])
  assert.equal(cloud.context.window.location.hash, '#/login')
})

test('前端只接受后端注入的明确 local 部署状态', () => {
  const source = fs.readFileSync(sourcePath('utils/backend.js'), 'utf8')
    .replace('import.meta.env?.VITE_BACKEND_BASE_URL', 'undefined')
    .replace('export const getApiBaseURL', 'globalThis.getApiBaseURL')
    .replace('export const getWebSocketURL', 'globalThis.getWebSocketURL')
    .replace('export const isLocalDeployment', 'globalThis.isLocalDeployment')
  for (const [mode, expected] of [['local', true], ['cloud', false], [undefined, false]]) {
    const context = {
      window: {
        __DEPLOYMENT_MODE__: mode,
        location: { protocol: 'http:', hostname: '8.137.96.104', port: '' }
      },
      localStorage: { getItem: () => null }
    }
    vm.runInNewContext(source, context)
    assert.equal(context.isLocalDeployment(), expected)
  }
})
