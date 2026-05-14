import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/',
  timeout: 10000
})

// 请求拦截器：自动携带 Token
request.interceptors.request.use(
  config => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  response => {
    const data = response.data
    // 校验后端业务码：如果返回了 code 字段且不为 200，当作错误处理
    if (data && typeof data.code === 'number' && data.code !== 200) {
      const msg = data.message || data.detail || '请求失败'
      ElMessage.error(msg)
      return Promise.reject(new Error(msg))
    }
    return data
  },
  error => {
    if (error.response?.status === 401) {
      ElMessage.error('登录已过期，请重新登录')
      localStorage.removeItem('access_token')
      window.location.hash = '#/login'
    } else {
      ElMessage.error(error.response?.data?.detail || error.message || '请求失败')
    }
    return Promise.reject(error)
  }
)

export default request
