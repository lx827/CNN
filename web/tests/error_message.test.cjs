const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const vm = require('node:vm')
const test = require('node:test')
const root = path.resolve(__dirname, '..')
const helpers = import(pathToFileURL(path.join(root, 'src/utils/errorMessage.js')).href)

const failure = () => ({ response: { status: 422, data: { detail: {
  status: 'not_evaluable', method: 'emd', reason: 'no_eligible_components',
} } } })

test('422对象保留方法和失败原因，旧字符串及请求校验错误仍可读', async () => {
  const { formatErrorMessage } = await helpers
  assert.equal(formatErrorMessage(failure()), '去噪 emd：no_eligible_components')
  assert.equal(formatErrorMessage({ response: { data: { detail: '旧错误文案' } } }), '旧错误文案')
  assert.equal(formatErrorMessage({ response: { data: { detail: [{ msg: '参数过小' }] } } }), '参数过小')
  assert.equal(formatErrorMessage({ message: '网络错误' }), '网络错误')
  assert.equal(formatErrorMessage({}, '诊断失败'), '诊断失败')
})

test('实际request拦截器显示可读422文字并保留原错误供页面处理', async () => {
  const utils = await helpers
  const messages = []
  let rejected
  const request = { interceptors: { request: { use() {} }, response: { use(_, error) { rejected = error } } } }
  const source = readFileSync(path.join(root, 'src/utils/request.js'), 'utf8')
    .replace(/^import .*\r?\n/gm, '').replace(/^export default request\s*$/m, '')
  vm.runInNewContext(source, {
    ...utils, axios: { create: () => request }, getApiBaseURL: () => '',
    ElMessage: { error: message => messages.push(message) },
  })
  const error = failure()
  await assert.rejects(rejected(error), actual => actual === error)
  assert.deepEqual(messages, ['去噪 emd：no_eligible_components'])
})
