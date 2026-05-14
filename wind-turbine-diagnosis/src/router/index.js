import { createRouter, createWebHashHistory } from 'vue-router'
import Layout from '../components/Layout.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { public: true }
  },
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    children: [
      {
        path: '/dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '设备总览' }
      },
      {
        path: '/monitor',
        name: 'Monitor',
        component: () => import('../views/Monitor.vue'),
        meta: { title: '实时监测' }
      },
      {
        path: '/diagnosis',
        name: 'Diagnosis',
        component: () => import('../views/Diagnosis.vue'),
        meta: { title: '故障诊断' }
      },
      {
        path: '/research-diagnosis',
        name: 'ResearchDiagnosis',
        component: () => import('../views/ResearchDiagnosis.vue'),
        meta: { title: '高级诊断' }
      },
      {
        path: '/alarm',
        name: 'Alarm',
        component: () => import('../views/Alarm.vue'),
        meta: { title: '告警记录' }
      },
      {
        path: '/data',
        name: 'DataView',
        component: () => import('../views/DataView.vue'),
        meta: { title: '数据查看' }
      },
      {
        path: '/settings',
        name: 'Settings',
        component: () => import('../views/Settings.vue'),
        meta: { title: '边端配置' }
      },
      {
        path: '/logs',
        name: 'Logs',
        component: () => import('../views/Logs.vue'),
        meta: { title: '系统日志' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// 全局路由守卫：未登录跳转到登录页
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  if (!to.meta?.public && !token) {
    next('/login')
  } else {
    next()
  }
})

export default router
