import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import './compact.css'
import ECharts from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DataZoomComponent,
  MarkLineComponent,
} from 'echarts/components'
import { isAuthenticated, isRoot, initAuth } from './utils/auth'

use([
  CanvasRenderer,
  LineChart,
  BarChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DataZoomComponent,
  MarkLineComponent,
])

// 路由設定
const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('./views/Login.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('./views/Dashboard.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/indicators/:name',
    name: 'IndicatorDetail',
    component: () => import('./views/IndicatorDetail.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/devices',
    name: 'Devices',
    component: () => import('./views/Devices.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/contacts',
    name: 'Contacts',
    component: () => import('./views/Contacts.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('./views/Settings.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/comparison',
    name: 'Comparison',
    component: () => import('./views/Comparison.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/users',
    name: 'Users',
    component: () => import('./views/Users.vue'),
    meta: { requiresAuth: true, requiresRoot: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守衛
router.beforeEach(async (to, from, next) => {
  // 初始化認證狀態（只在第一次載入時）
  if (!router._authInitialized) {
    await initAuth()
    router._authInitialized = true
  }

  // 需要登入的頁面
  if (to.meta.requiresAuth && !isAuthenticated.value) {
    return next({ name: 'Login', query: { redirect: to.fullPath } })
  }

  // 需要 root 權限的頁面
  if (to.meta.requiresRoot && !isRoot.value) {
    return next({ name: 'Dashboard' })
  }

  // 已登入時不能進入登入頁
  if (to.meta.guest && isAuthenticated.value) {
    return next({ name: 'Dashboard' })
  }

  next()
})

const app = createApp(App)
app.component('v-chart', ECharts)
app.use(router)
app.mount('#app')
