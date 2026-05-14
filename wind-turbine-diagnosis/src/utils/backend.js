const DEFAULT_BACKEND_URL = 'http://8.137.96.104:8000'

const stripTrailingSlash = (url) => url.replace(/\/+$/, '')

const getConfiguredBackend = () => {
  const runtimeUrl = window.__BACKEND_BASE_URL__
  const storedUrl = localStorage.getItem('backend_base_url')
  const envUrl = import.meta.env?.VITE_BACKEND_BASE_URL
  return runtimeUrl || storedUrl || envUrl || ''
}

const shouldUseSameOrigin = () => {
  const { protocol, hostname, port } = window.location
  if (protocol === 'file:') return false
  if ((hostname === 'localhost' || hostname === '127.0.0.1') && port !== '3000') {
    return false
  }
  return true
}

export const getApiBaseURL = () => {
  const configured = getConfiguredBackend()
  if (configured) return `${stripTrailingSlash(configured)}/`
  return shouldUseSameOrigin() ? '/' : `${DEFAULT_BACKEND_URL}/`
}

export const getWebSocketURL = (path = '/ws/monitor') => {
  const configured = getConfiguredBackend()
  if (configured || !shouldUseSameOrigin()) {
    const base = stripTrailingSlash(configured || DEFAULT_BACKEND_URL)
    const wsBase = base.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:')
    return `${wsBase}${path}`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}

