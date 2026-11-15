<template>
  <div class="layout">
    <!-- 左侧导航边栏 -->
    <aside class="sidebar" :class="{ collapsed: isCollapsed }">
      <div class="logo" @click="router.push('/dashboard')">
        <div class="logo-mark">
          <el-icon :size="20"><Setting /></el-icon>
        </div>
        <transition name="fade">
          <div v-if="!isCollapsed" class="logo-text">
            <span class="logo-title">风机齿轮箱诊断</span>
            <span class="logo-sub">Intelligent Diagnosis</span>
          </div>
        </transition>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapsed"
        :collapse-transition="false"
        class="side-menu"
        @select="handleMenuSelect"
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-footer">
        <el-tooltip :content="isCollapsed ? '展开导航' : '收起导航'" placement="right" :disabled="!isCollapsed">
          <button class="collapse-btn" @click="isCollapsed = !isCollapsed">
            <el-icon :size="16">
              <Expand v-if="isCollapsed" />
              <Fold v-else />
            </el-icon>
          </button>
        </el-tooltip>
      </div>
    </aside>

    <!-- 右侧：顶栏 + 主内容 -->
    <div class="content-wrap">
      <header class="topbar">
        <div class="page-title">{{ pageTitle }}</div>
        <div class="topbar-right">
          <el-tooltip content="退出登录" placement="bottom">
            <button class="logout-btn" @click="handleLogout">
              <el-icon :size="16"><SwitchButton /></el-icon>
              <span>退出</span>
            </button>
          </el-tooltip>
        </div>
      </header>

      <el-main class="main">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const isCollapsed = ref(false)

const menuItems = [
  { path: '/dashboard', title: '设备总览', icon: 'Monitor' },
  { path: '/monitor', title: '实时监测', icon: 'TrendCharts' },
  { path: '/research-diagnosis', title: '高级诊断', icon: 'Cpu' },
  { path: '/acquisition', title: '真实采集', icon: 'VideoPlay' },
  { path: '/alarm', title: '告警记录', icon: 'Bell' },
  { path: '/data', title: '数据查看', icon: 'DataLine' },
  { path: '/settings', title: '边端配置', icon: 'Setting' },
  { path: '/logs', title: '系统日志', icon: 'Document' },
]

const activeMenu = computed(() => route.path)
const pageTitle = computed(() => route.meta?.title || '')

const handleMenuSelect = (index) => {
  router.push(index)
}

const handleLogout = () => {
  localStorage.removeItem('access_token')
  router.push('/login')
}
</script>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
  background: var(--bg-page);
}

/* ---------- 边栏 ---------- */
.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  width: var(--sidebar-width);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
  border-right: 1px solid var(--border-light);
  transition: width var(--transition-base);
  z-index: 100;
}

.sidebar.collapsed {
  width: var(--sidebar-width-collapsed);
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  height: var(--topbar-height);
  padding: 0 16px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-light);
  overflow: hidden;
  white-space: nowrap;
}

.logo-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--brand-500), var(--brand-700));
  color: #fff;
  box-shadow: var(--shadow-brand);
}

.logo-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.logo-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.logo-sub {
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.side-menu {
  flex: 1;
  border-right: none;
  padding: 12px 10px;
  background: transparent;
}

.side-menu:not(.el-menu--collapse) {
  width: 100%;
}

.side-menu :deep(.el-menu-item) {
  height: 42px;
  line-height: 42px;
  margin: 2px 0;
  border-radius: var(--radius-md);
  color: var(--text-regular);
  font-size: 14px;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.side-menu :deep(.el-menu-item:hover) {
  background: var(--bg-subtle);
  color: var(--text-primary);
}

.side-menu :deep(.el-menu-item.is-active) {
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-weight: 600;
}

.side-menu :deep(.el-menu-item.is-active)::before {
  content: '';
  position: absolute;
  left: -10px;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  border-radius: 0 3px 3px 0;
  background: var(--color-primary);
}

.sidebar-footer {
  padding: 12px 10px;
  border-top: 1px solid var(--border-light);
}

.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 36px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.collapse-btn:hover {
  background: var(--bg-subtle);
  color: var(--text-primary);
}

/* ---------- 右侧 ---------- */
.content-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 99;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--topbar-height);
  padding: 0 24px;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border-light);
}

.page-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
}

.logout-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  color: var(--text-regular);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.logout-btn:hover {
  color: var(--color-danger);
  border-color: var(--color-danger);
  background: var(--color-danger-soft);
}

.main {
  flex: 1;
  padding: 24px;
  width: 100%;
  max-width: var(--content-max-width);
  margin: 0 auto;
}

.fade-enter-active {
  transition: opacity var(--transition-fast);
}
.fade-enter-from {
  opacity: 0;
}

/* 窄屏：边栏自动折叠为纯图标 */
@media (max-width: 1100px) {
  .sidebar {
    width: var(--sidebar-width-collapsed);
  }
  .logo-text {
    display: none;
  }
  .side-menu :deep(.el-menu-item span),
  .side-menu :deep(.el-sub-menu__title span) {
    display: none;
  }
  .side-menu :deep(.el-menu-item) {
    justify-content: center;
  }
  .sidebar-footer {
    display: none;
  }
}
</style>
