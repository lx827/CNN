// 使用浏览器 WebSocket 替身覆盖连接状态与旧连接回调竞争。
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')
const source = fs.readFileSync(path.resolve(__dirname, '../../wind-turbine-diagnosis/src/utils/websocket.js'), 'utf8')
  .replace(/^import .*\r?\n/gm, '')
  .replace('export const getWebSocketClient', 'globalThis.getWebSocketClient')

function harness() {
  const sockets = [], timeouts = new Map(), intervals = new Map()
  let id = 0
  class Socket {
    static CONNECTING = 0
    static OPEN = 1
    constructor() { this.readyState = 0; sockets.push(this) }
    close() { this.readyState = 3 }
    send() {}
    open() { this.readyState = 1; this.onopen() }
  }
  const context = {
    WebSocket: Socket, URL, getWebSocketURL: () => 'ws://localhost/ws/monitor',
    localStorage: { getItem: () => null }, window: { location: { href: 'http://localhost' } },
    console: { log() {}, warn() {}, error() {} },
    setTimeout: cb => { timeouts.set(++id, cb); return id }, clearTimeout: key => timeouts.delete(key),
    setInterval: cb => { intervals.set(++id, cb); return id }, clearInterval: key => intervals.delete(key)
  }
  vm.runInNewContext(source, context)
  return { client: context.getWebSocketClient(), sockets, timeouts, intervals }
}

test('握手期间重复 connect 不创建多条连接', () => {
  const h = harness()
  h.client.connect()
  h.client.connect()
  assert.equal(h.sockets.length, 1)
})

test('关闭后立即重连，旧回调不能中断新心跳或触发重连', () => {
  const h = harness()
  h.client.connect()
  const old = h.sockets[0]
  old.open()
  h.client.close()
  h.client.connect()
  h.sockets[1].open()
  old.onclose()
  assert.equal(h.intervals.size, 1)
  assert.equal(h.timeouts.size, 0)
})

test('重连定时器去重，主动关闭阻止后续重连', () => {
  const h = harness()
  h.client.scheduleReconnect()
  h.client.scheduleReconnect()
  assert.equal(h.timeouts.size, 1)
  h.client.close()
  h.client.scheduleReconnect()
  assert.equal(h.timeouts.size, 0)
})
