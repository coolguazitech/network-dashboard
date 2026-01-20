import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import './compact.css'

// 路由設定
const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('./views/Dashboard.vue'),
  },
  {
    path: '/indicators/:name',
    name: 'IndicatorDetail',
    component: () => import('./views/IndicatorDetail.vue'),
  },
  {
    path: '/switches',
    name: 'Switches',
    component: () => import('./views/Switches.vue'),
  },
  {
    path: '/comparison',
    name: 'Comparison',
    component: () => import('./views/Comparison.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const app = createApp(App)
app.use(router)
app.mount('#app')
