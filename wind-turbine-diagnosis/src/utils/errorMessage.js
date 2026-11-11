// 解析本次去噪422对象，同时保留既有字符串/请求校验错误的可读提示。
export function formatErrorMessage(error, fallback = '请求失败') {
  const detail = error?.response?.data?.detail ?? error?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    const messages = detail.map(item => item?.msg).filter(message => typeof message === 'string')
    if (messages.length) return messages.join('；')
  }
  if (detail && typeof detail.reason === 'string') {
    return detail.method ? `去噪 ${detail.method}：${detail.reason}` : detail.reason
  }
  return typeof error?.message === 'string' && error.message ? error.message : fallback
}
