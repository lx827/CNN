/**
 * 认证接口(/api/auth)
 * 登录换取 JWT Token,由各视图经 localStorage 携带
 */
import request from '../utils/request'

export const login = (data) => request.post('/api/auth/login', data)
