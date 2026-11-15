<template>
  <div class="login-container">
    <!-- 背景装饰 -->
    <div class="bg-decor bg-decor-1"></div>
    <div class="bg-decor bg-decor-2"></div>

    <el-card class="login-card">
      <div class="login-header">
        <div class="logo-mark">
          <el-icon :size="26" color="#fff"><Setting /></el-icon>
        </div>
        <h2>风机齿轮箱智能故障诊断系统</h2>
        <p>Wind Turbine Gearbox Intelligent Diagnosis</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        size="large"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入访问密码"
            show-password
            prefix-icon="Lock"
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            class="login-btn"
            @click="handleLogin"
          >
            进入系统
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-tip">
        <el-tag type="info" size="small" effect="plain">默认密码：admin123</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '../api/auth'

const router = useRouter()
const route = useRoute()
const formRef = ref()
const loading = ref(false)

const form = reactive({
  password: ''
})

const rules = {
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    const res = await login({ password: form.password })
    if (res.access_token) {
      localStorage.setItem('access_token', res.access_token)
      ElMessage.success('登录成功')
      const target = route.query.redirect
      router.push(typeof target === 'string' && target.startsWith('/') && !target.startsWith('//') && target !== '/login' ? target : '/dashboard')
    } else {
      ElMessage.error(res.message || '登录失败')
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '密码错误')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-page);
  overflow: hidden;
}

/* 柔和的品牌色光斑背景 */
.bg-decor {
  position: absolute;
  border-radius: 50%;
  filter: blur(120px);
  pointer-events: none;
}

.bg-decor-1 {
  width: 480px;
  height: 480px;
  top: -160px;
  right: -120px;
  background: rgba(99, 102, 241, 0.16);
}

.bg-decor-2 {
  width: 420px;
  height: 420px;
  bottom: -140px;
  left: -100px;
  background: rgba(14, 165, 233, 0.12);
}

.login-card {
  position: relative;
  width: 400px;
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
}

.login-card :deep(.el-card__body) {
  padding: 40px 36px 28px;
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.logo-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--brand-500), var(--brand-700));
  box-shadow: var(--shadow-brand);
}

.login-header h2 {
  margin: 18px 0 6px;
  font-size: 20px;
  color: var(--text-primary);
  font-weight: 700;
  letter-spacing: 0.01em;
}

.login-header p {
  color: var(--text-secondary);
  font-size: 12px;
  letter-spacing: 0.04em;
}

.login-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  letter-spacing: 0.1em;
}

.login-tip {
  text-align: center;
  margin-top: 8px;
}
</style>
