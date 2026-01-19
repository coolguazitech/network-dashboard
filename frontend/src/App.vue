<template>
  <div class="min-h-screen bg-gray-100">
    <!-- 頂部導航 -->
    <nav class="bg-white shadow-sm">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-16">
          <div class="flex">
            <div class="flex-shrink-0 flex items-center">
              <h1 class="text-xl font-bold text-gray-800">
                🌐 Network Dashboard
              </h1>
            </div>
            <div class="hidden sm:ml-6 sm:flex sm:space-x-8">
              <router-link
                to="/"
                class="nav-link"
                :class="{ active: $route.path === '/' }"
              >
                Dashboard
              </router-link>
              <router-link
                to="/switches"
                class="nav-link"
                :class="{ active: $route.path === '/switches' }"
              >
                Switches
              </router-link>
              <router-link
                to="/comparison"
                class="nav-link"
                :class="{ active: $route.path === '/comparison' }"
              >
                客戶端比較
              </router-link>
            </div>
          </div>
          <div class="flex items-center">
            <span class="text-sm text-gray-500">
              最後更新: {{ lastUpdate }}
            </span>
          </div>
        </div>
      </div>
    </nav>

    <!-- 主內容區 -->
    <main class="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import dayjs from 'dayjs'

const lastUpdate = ref('--')

const updateTime = () => {
  lastUpdate.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
}

onMounted(() => {
  updateTime()
  setInterval(updateTime, 60000)
})
</script>

<style>
.nav-link {
  @apply inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium text-gray-500 hover:text-gray-700 hover:border-gray-300;
}

.nav-link.active {
  @apply border-blue-500 text-gray-900;
}
</style>
