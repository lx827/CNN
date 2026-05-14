<template>
  <div class="layout">
    <!-- 顶部导航栏 -->
    <el-header class="header">
      <div class="header-content">
        <div class="logo">
          <el-icon :size="28" color="#fff"><Setting /></el-icon>
          <span class="title">风机齿轮箱智能故障诊断系统</span>
        </div>
        <div class="header-right">
          <el-menu
            :default-active="activeMenu"
            mode="horizontal"
            :ellipsis="false"
            @select="handleMenuSelect"
            class="nav-menu"
          >
            <el-menu-item index="/dashboard">
              <el-icon><Monitor /></el-icon>
              <span>设备总览</span>
            </el-menu-item>
            <el-menu-item index="/monitor">
              <el-icon><TrendCharts /></el-icon>
              <span>实时监测</span>
            </el-menu-item>
            <el-menu-item index="/diagnosis">
              <el-icon><Warning /></el-icon>
              <span>故障诊断</span>
            </el-menu-item>
            <el-menu-item index="/alarm">
              <el-icon><Bell /></el-icon>
              <span>告警记录</span>
            </el-menu-item>
            <el-menu-item index="/data">
              <el-icon><DataLine /></el-icon>
              <span>数据查看</span>
            </el-menu-item>
            <el-menu-item index="/settings">
              <el-icon><Setting /></el-icon>
              <span>边端配置</span>
            </el-menu-item>
            <el-menu-item index="/logs">
              <el-icon><Document /></el-icon>
              <span>系统日志</span>
            </el-menu-item>
          </el-menu>

          <el-button class="logout-btn" type="danger" plain size="small" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            <span>退出登录</span>
          </el-button>
        </div>
      </div>
    </el-header>

    <!-- 主内容区 -->
    <el-main class="main">
      <router-view />
    </el-main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '../stores/userStore'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeMenu = computed(() => route.path)

const handleMenuSelect = (index) => {
  router.push(index)
}

const handleLogout = () => {
  userStore.clearToken()
  router.push('/login')
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
  background: #f0f2f5;
}

.header {
  background: linear-gradient(135deg, #165DFF 0%, #0E42D2 100%);
  padding: 0;
  height: 64px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
  padding: 0 24px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title {
  color: #fff;
  font-size: 20px;
  font-weight: 600;
  white-space: nowrap;
}

.nav-menu {
  background: transparent;
  border: none;
}

.nav-menu :deep(.el-menu-item) {
  color: rgba(255, 255, 255, 0.85);
  font-size: 15px;
  border-bottom: none;
}

.nav-menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
}

.nav-menu :deep(.el-menu-item.is-active) {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  border-bottom: 3px solid #fff;
}

.logout-btn {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}

.logout-btn:hover {
  background: rgba(255, 255, 255, 0.25);
  border-color: rgba(255, 255, 255, 0.5);
  color: #fff;
}

.main {
  padding: 24px;
  max-width: 1600px;
  margin: 0 auto;
  width: 100%;
}

@media (max-width: 1200px) {
  .title {
    font-size: 16px;
  }

  .nav-menu :deep(.el-menu-item span) {
    display: none;
  }
}
</style>
