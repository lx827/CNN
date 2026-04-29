import { createRouter, createWebHistory } from 'vue-router'
import Layout from '../components/Layout.vue'

const routes = [
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
        path: '/alarm',
        name: 'Alarm',
        component: () => import('../views/Alarm.vue'),
        meta: { title: '告警记录' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
