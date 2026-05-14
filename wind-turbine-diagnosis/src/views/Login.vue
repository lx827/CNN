<template>
  <div class="login-container">
    <el-card class="login-card" shadow="always">
      <div class="login-header">
        <el-icon :size="40" color="#165DFF"><Setting /></el-icon>
        <h2>风机齿轮箱智能故障诊断系统</h2>
        <p>请输入访问密码</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="访问密码"
            size="large"
            show-password
            prefix-icon="Lock"
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            style="width: 100%"
            @click="handleLogin"
          >
            进入系统
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-tip">
        <el-tag type="info" size="small">默认密码：admin123</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '../api/index'
import { useUserStore } from '../stores/userStore'

const router = useRouter()
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
      const userStore = useUserStore()
      userStore.setToken(res.access_token)
      ElMessage.success('登录成功')
      router.push('/dashboard')
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
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #f0f2f5 0%, #e4e7ed 100%);
}

.login-card {
  width: 420px;
  padding: 20px;
  border-radius: 12px;
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-header h2 {
  margin: 16px 0 8px;
  font-size: 22px;
  color: #1d2129;
  font-weight: 600;
}

.login-header p {
  color: #86909c;
  font-size: 14px;
}

.login-tip {
  text-align: center;
  margin-top: 16px;
}
</style>
