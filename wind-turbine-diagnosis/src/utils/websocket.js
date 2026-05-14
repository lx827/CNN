/**
 * WebSocket 客户端（带断线自动重连）
 * 使用指数退避策略，最大重试间隔 30 秒
 */

import { getWebSocketURL } from './backend'

const buildWebSocketURL = () => {
  const token = localStorage.getItem('access_token')
  const url = new URL(getWebSocketURL(), window.location.href)
  if (token) url.searchParams.set('token', token)
  return url.toString()
}

class WebSocketClient {
  constructor() {
    this.ws = null
    this.reconnectTimer = null
    this.heartbeatTimer = null
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 20
    this.baseReconnectDelay = 1000
    this.maxReconnectDelay = 30000
    this.listeners = new Map()
    this.isManualClose = false
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return
    this.isManualClose = false

    try {
      this.ws = new WebSocket(buildWebSocketURL())

      this.ws.onopen = () => {
        console.log('[WebSocket] 已连接')
        this.reconnectAttempts = 0
        this.emit('open', {})
        this.startHeartbeat()
      }

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          this.emit(msg.type || 'message', msg.data || msg)
        } catch (e) {
          this.emit('message', event.data)
        }
      }

      this.ws.onclose = () => {
        console.log('[WebSocket] 连接断开')
        this.stopHeartbeat()
        this.emit('close', {})
        if (!this.isManualClose) {
          this.scheduleReconnect()
        }
      }

      this.ws.onerror = (err) => {
        console.error('[WebSocket] 连接错误:', err)
        this.emit('error', err)
      }
    } catch (e) {
      console.error('[WebSocket] 创建连接失败:', e)
      this.scheduleReconnect()
    }
  }

  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('[WebSocket] 已达到最大重连次数，停止重连')
      this.emit('max_retries', {})
      return
    }

    const delay = Math.min(
      this.baseReconnectDelay * Math.pow(1.5, this.reconnectAttempts),
      this.maxReconnectDelay
    )
    this.reconnectAttempts++
    console.log(`[WebSocket] ${delay}ms 后尝试第 ${this.reconnectAttempts} 次重连...`)

    this.reconnectTimer = setTimeout(() => {
      this.connect()
    }, delay)
  }

  startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000) // 每 30 秒发一次心跳
  }

  stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, [])
    }
    this.listeners.get(event).push(callback)
    return () => this.off(event, callback)
  }

  off(event, callback) {
    const cbs = this.listeners.get(event)
    if (cbs) {
      const idx = cbs.indexOf(callback)
      if (idx !== -1) cbs.splice(idx, 1)
    }
  }

  emit(event, data) {
    const cbs = this.listeners.get(event)
    if (cbs) {
      cbs.forEach(cb => {
        try { cb(data) } catch (e) { console.error(e) }
      })
    }
  }

  send(data) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }

  close() {
    this.isManualClose = true
    this.stopHeartbeat()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }
}

// 单例导出
let client = null
export const getWebSocketClient = () => {
  if (!client) {
    client = new WebSocketClient()
  }
  return client
}
