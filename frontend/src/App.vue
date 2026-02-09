<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950" @click="isAuthenticated && closeUserMenu($event)">
    <!-- 流星雨背景 -->
    <MeteorShower />

    <!-- 頂部導航（登入後才顯示） -->
    <nav v-if="isAuthenticated && route.name !== 'Login'" class="bg-slate-900/80 backdrop-blur-sm border-b border-cyan-500/10">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-14">
          <!-- 左側：Logo + 導航 -->
          <div class="flex items-center">
            <router-link to="/" class="flex-shrink-0 flex items-center mr-8 ml-2 cursor-pointer hover:opacity-80 transition">
              <div class="pt-0.5 text-center">
                <div class="text-xl font-black tracking-[0.12em] leading-none logo-wrapper">
                  <span class="logo-text bg-gradient-to-r from-cyan-400 via-blue-500 via-purple-400 to-cyan-300 bg-clip-text text-transparent">NETORA</span>
                  <span class="logo-glow" aria-hidden="true">
                    <span class="glow-letter glow-1">N</span>
                    <span class="glow-letter glow-2">E</span>
                    <span class="glow-letter glow-3">T</span>
                    <span class="glow-letter glow-4">O</span>
                    <span class="glow-letter glow-5">R</span>
                    <span class="glow-letter glow-6">A</span>
                  </span>
                </div>
                <div class="text-[9px] text-cyan-500/50 tracking-[0.18em] mt-0.5">CHANGE MONITOR</div>
              </div>
            </router-link>
            <div class="hidden sm:flex sm:space-x-1">
              <router-link
                to="/"
                class="nav-link"
                :class="{ active: route.path === '/' }"
              >
                總覽
              </router-link>
              <router-link
                to="/comparison"
                class="nav-link"
                :class="{ active: route.path === '/comparison' }"
              >
                比對
              </router-link>
              <router-link
                to="/devices"
                class="nav-link"
                :class="{ active: route.path === '/devices' }"
              >
                設備
              </router-link>
              <router-link
                to="/contacts"
                class="nav-link"
                :class="{ active: route.path === '/contacts' }"
              >
                通訊錄
              </router-link>
              <router-link
                to="/settings"
                class="nav-link"
                :class="{ active: route.path === '/settings' }"
              >
                設定
              </router-link>
              <router-link
                v-if="isRoot"
                to="/users"
                class="nav-link"
                :class="{ active: route.path === '/users' }"
              >
                使用者
              </router-link>
              <router-link
                v-if="isRoot"
                to="/system-logs"
                class="nav-link"
                :class="{ active: route.path === '/system-logs' }"
              >
                日誌
              </router-link>
            </div>
          </div>
          <!-- 右側：歲修選擇器 + 使用者 -->
          <div class="flex items-center space-x-3">
            <select
              v-model="selectedMaintenanceId"
              @change="onMaintenanceIdChange"
              :disabled="!isRoot"
              class="px-2 py-1 text-sm bg-slate-700 border border-slate-600 text-slate-200 rounded focus:outline-none focus:ring-2 focus:ring-cyan-500 max-w-[160px] truncate disabled:opacity-60 disabled:cursor-not-allowed"
              :title="isRoot ? '選擇歲修' : '您只能查看被指派的歲修'"
            >
              <option value="">選擇歲修</option>
              <option
                v-for="m in maintenanceList"
                :key="m.id"
                :value="m.id"
              >
                {{ m.is_active === false ? '[已暫停] ' : '' }}{{ m.name && m.name !== m.id ? m.name : m.id }}
              </option>
            </select>
            <button
              v-if="isRoot"
              @click="showMaintenanceModal = true"
              class="text-slate-400 hover:text-cyan-400 p-1.5 rounded hover:bg-slate-700 transition"
              title="管理歲修"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </button>

            <!-- 分隔線 -->
            <div class="h-6 w-px bg-slate-700"></div>

            <!-- 使用者選單 -->
            <div class="relative user-menu-container">
              <button
                @click.stop="showUserMenu = !showUserMenu"
                class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-slate-700/50 transition"
              >
                <div class="w-7 h-7 rounded-full bg-cyan-600 flex items-center justify-center text-white text-xs font-medium">
                  {{ displayName.charAt(0).toUpperCase() }}
                </div>
                <span class="text-sm text-slate-300 hidden md:block">{{ displayName }}</span>
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              <!-- 下拉選單 -->
              <div
                v-if="showUserMenu"
                class="absolute right-0 mt-2 w-48 bg-slate-800 border border-slate-700 rounded-lg shadow-xl py-1 z-50"
              >
                <div class="px-3 py-2 border-b border-slate-700">
                  <div class="text-sm font-medium text-white">{{ displayName }}</div>
                  <div class="text-xs text-slate-400">{{ currentUser?.username }}</div>
                  <div v-if="isRoot" class="mt-1">
                    <span class="px-1.5 py-0.5 bg-amber-600/30 text-amber-400 text-xs rounded">ROOT</span>
                  </div>
                </div>
                <button
                  @click="handleLogout"
                  class="w-full px-3 py-2 text-left text-sm text-red-400 hover:bg-slate-700/50 transition flex items-center gap-2"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                  </svg>
                  登出
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </nav>

    <!-- 主內容區 -->
    <main :class="isAuthenticated && route.name !== 'Login' ? 'max-w-7xl mx-auto py-6 sm:px-6 lg:px-8' : ''">
      <router-view />
    </main>

    <!-- 右側固定餐點狀態欄 -->
    <MealStatus v-if="isAuthenticated && selectedMaintenanceId && route.name !== 'Login'" />

    <!-- 歲修管理 Modal -->
    <div 
      v-if="showMaintenanceModal"
      class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50"
      @click.self="showMaintenanceModal = false"
    >
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-2xl w-full max-w-2xl p-5 max-h-[80vh] overflow-auto">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-white">📋 歲修管理</h3>
          <button @click="showMaintenanceModal = false" class="text-slate-400 hover:text-slate-200">✕</button>
        </div>
        
        <!-- 新增歲修表單 -->
        <div class="bg-slate-900/50 rounded p-3 mb-4">
          <h4 class="text-sm font-medium text-slate-300 mb-2">新增歲修</h4>
          <div class="flex gap-2">
            <input 
              v-model="newMaintenance.id" 
              type="text" 
              placeholder="歲修 ID（例如：2026Q1）"
              class="flex-1 px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
            />
            <input 
              v-model="newMaintenance.name" 
              type="text" 
              placeholder="名稱（選填）"
              class="flex-1 px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
            />
            <button 
              @click="createMaintenance" 
              class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition"
              :disabled="!newMaintenance.id"
            >
              ➕ 新增
            </button>
          </div>
        </div>
        
        <!-- 歲修列表 -->
        <table class="min-w-full text-sm">
          <thead class="bg-slate-900/60">
            <tr>
              <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">歲修 ID</th>
              <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">名稱</th>
              <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">採集狀態</th>
              <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">建立時間</th>
              <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-700">
            <tr v-for="m in maintenanceList" :key="m.id" class="hover:bg-slate-700/50 transition">
              <td class="px-3 py-2 font-mono text-cyan-300">
                {{ m.id }}
                <span v-if="m.id === selectedMaintenanceId" class="ml-1 text-xs text-green-400">●當前</span>
              </td>
              <td class="px-3 py-2 text-slate-200">{{ m.name || '-' }}</td>
              <td class="px-3 py-2">
                <button
                  @click="toggleMaintenanceActive(m)"
                  class="inline-flex items-center gap-2 cursor-pointer group"
                  :title="m.is_active ? '點擊暫停採集' : '點擊恢復採集'"
                >
                  <!-- Toggle track -->
                  <span
                    class="relative inline-block w-8 h-[18px] rounded-full transition-colors duration-200"
                    :class="m.is_active ? 'bg-green-600' : 'bg-slate-600'"
                  >
                    <!-- Toggle knob -->
                    <span
                      class="absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white shadow transition-transform duration-200"
                      :class="m.is_active ? 'translate-x-[14px]' : 'translate-x-0'"
                    ></span>
                  </span>
                  <span class="text-xs" :class="m.is_active ? 'text-green-400' : 'text-slate-500'">
                    {{ m.is_active ? '採集中' : '已暫停' }}
                  </span>
                </button>
              </td>
              <td class="px-3 py-2 text-slate-400 text-xs">{{ formatDate(m.created_at) }}</td>
              <td class="px-3 py-2">
                <button
                  @click="startDeleteMaintenance(m)"
                  class="text-red-400 hover:text-red-300 text-xs"
                >
                  刪除
                </button>
              </td>
            </tr>
            <tr v-if="maintenanceList.length === 0">
              <td colspan="5" class="px-3 py-6 text-center text-slate-500">尚無歲修記錄</td>
            </tr>
          </tbody>
        </table>
        
        <!-- 警告 -->
        <div class="bg-amber-900/30 border border-amber-700/50 rounded p-2 mt-4 text-xs">
          <p class="text-amber-400">⚠️ 刪除歲修將同時刪除所有相關資料，此操作無法復原！</p>
        </div>
      </div>
    </div>

    <!-- 刪除確認 Modal -->
    <div 
      v-if="showDeleteModal"
      class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-[60]"
    >
      <div class="bg-slate-800 border border-red-700 rounded-lg shadow-2xl w-full max-w-md p-5">
        <h3 class="text-lg font-bold text-red-400 mb-4">⚠️ 刪除歲修確認</h3>
        
        <div class="bg-red-900/30 border border-red-700/50 rounded p-3 mb-4">
          <p class="text-red-300 text-sm">
            即將刪除歲修：<span class="font-mono font-bold text-red-200">{{ deleteTarget?.id }}</span>
          </p>
          <p class="text-red-400 text-xs mt-2">將同時刪除：設備對應、Uplink期望、採集數據等所有相關資料</p>
          <p class="text-red-300 font-bold text-sm mt-2">此操作無法復原！</p>
        </div>
        
        <div class="mb-4">
          <label class="block text-sm text-slate-400 mb-1">
            請輸入「<span class="font-mono text-red-300">{{ deleteTarget?.id }}</span>」以確認刪除：
          </label>
          <input 
            v-model="deleteConfirmInput" 
            type="text" 
            class="w-full px-3 py-2 bg-slate-900 border border-red-600 rounded text-white text-sm font-mono focus:outline-none focus:ring-1 focus:ring-red-400"
            @keyup.enter="confirmDelete"
          />
        </div>
        
        <div class="flex justify-end gap-2">
          <button @click="cancelDelete" class="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded transition">
            取消
          </button>
          <button 
            @click="confirmDelete" 
            class="px-4 py-2 bg-red-600 hover:bg-red-500 text-white text-sm rounded transition disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="deleteConfirmInput !== deleteTarget?.id"
          >
            確認刪除
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, provide, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import MealStatus from '@/components/MealStatus.vue'
import MeteorShower from '@/components/MeteorShower.vue'
import { isAuthenticated, currentUser, isRoot, logout as authLogout, getAuthHeaders } from '@/utils/auth'

dayjs.extend(utc)

const router = useRouter()
const route = useRoute()

// 使用者選單
const showUserMenu = ref(false)

const displayName = computed(() => {
  return currentUser.value?.display_name || currentUser.value?.username || '使用者'
})

const handleLogout = () => {
  showUserMenu.value = false
  authLogout()
  router.push('/login')
}

// 點擊外部關閉選單
const closeUserMenu = (e) => {
  if (!e.target.closest('.user-menu-container')) {
    showUserMenu.value = false
  }
}

const selectedMaintenanceId = ref('')
const maintenanceList = ref([])

// 歲修管理 Modal
const showMaintenanceModal = ref(false)
const newMaintenance = ref({ id: '', name: '' })

// 刪除確認 Modal
const showDeleteModal = ref(false)
const deleteTarget = ref(null)
const deleteConfirmInput = ref('')

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  // 後端回傳 UTC 時間，需轉換為本地時間
  return dayjs.utc(dateStr).local().format('YYYY-MM-DD HH:mm')
}

const loadMaintenanceList = async () => {
  try {
    const res = await fetch('/api/v1/maintenance', {
      headers: getAuthHeaders(),
    })
    if (res.ok) {
      maintenanceList.value = await res.json()
      
      // 如果當前選中的不在列表中，重置選擇
      if (selectedMaintenanceId.value) {
        const found = maintenanceList.value.find(m => m.id === selectedMaintenanceId.value)
        if (!found) {
          if (maintenanceList.value.length > 0) {
            // 選擇第一個
            selectedMaintenanceId.value = maintenanceList.value[0].id
            onMaintenanceIdChange()
          } else {
            // 列表為空，清除選擇
            selectedMaintenanceId.value = ''
            localStorage.removeItem('selectedMaintenanceId')
          }
        }
      } else if (maintenanceList.value.length > 0) {
        // 沒有選擇時，選擇第一個
        const savedId = localStorage.getItem('selectedMaintenanceId')
        const found = maintenanceList.value.find(m => m.id === savedId)
        if (found) {
          selectedMaintenanceId.value = savedId
        } else {
          selectedMaintenanceId.value = maintenanceList.value[0].id
          onMaintenanceIdChange()
        }
      }
    }
  } catch (e) {
    console.error('載入歲修列表失敗:', e)
  }
}

const onMaintenanceIdChange = () => {
  // 保存到 localStorage
  localStorage.setItem('selectedMaintenanceId', selectedMaintenanceId.value)
}

// 新增歲修
const createMaintenance = async () => {
  if (!newMaintenance.value.id) return
  
  try {
    const res = await fetch('/api/v1/maintenance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(newMaintenance.value),
    })
    
    if (res.ok) {
      newMaintenance.value = { id: '', name: '' }
      await loadMaintenanceList()
    } else {
      const err = await res.json()
      alert(`建立失敗: ${err.detail || '未知錯誤'}`)
    }
  } catch (e) {
    console.error('建立歲修失敗:', e)
    alert('建立失敗，請稍後再試')
  }
}

// 切換歲修採集狀態
const toggleMaintenanceActive = async (m) => {
  try {
    const res = await fetch(`/api/v1/maintenance/${encodeURIComponent(m.id)}/toggle-active`, {
      method: 'PATCH',
      headers: getAuthHeaders(),
    })
    if (res.ok) {
      await loadMaintenanceList()
    } else {
      const err = await res.json()
      alert(`切換失敗: ${err.detail || '未知錯誤'}`)
    }
  } catch (e) {
    console.error('切換採集狀態失敗:', e)
    alert('切換失敗，請稍後再試')
  }
}

// 開始刪除歲修（打開確認 Modal）
const startDeleteMaintenance = (m) => {
  deleteTarget.value = m
  deleteConfirmInput.value = ''
  showDeleteModal.value = true
}

// 取消刪除
const cancelDelete = () => {
  showDeleteModal.value = false
  deleteTarget.value = null
  deleteConfirmInput.value = ''
}

// 確認刪除
const confirmDelete = async () => {
  if (!deleteTarget.value || deleteConfirmInput.value !== deleteTarget.value.id) {
    return
  }
  
  try {
    const res = await fetch(`/api/v1/maintenance/${encodeURIComponent(deleteTarget.value.id)}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    })
    
    if (res.ok) {
      showDeleteModal.value = false
      deleteTarget.value = null
      deleteConfirmInput.value = ''
      await loadMaintenanceList()
    } else {
      const err = await res.json()
      alert(`刪除失敗: ${err.detail || '未知錯誤'}`)
    }
  } catch (e) {
    console.error('刪除歲修失敗:', e)
    alert('刪除失敗，請稍後再試')
  }
}

// 提供給所有子組件使用
provide('maintenanceId', selectedMaintenanceId)
provide('refreshMaintenanceList', loadMaintenanceList)

// 當打開歲修管理 Modal 時重新載入列表
watch(showMaintenanceModal, async (isOpen) => {
  if (isOpen && isAuthenticated.value) {
    await loadMaintenanceList()
  }
})

// 當登入狀態改變時重新載入列表
watch(isAuthenticated, async (authenticated) => {
  if (authenticated) {
    const savedId = localStorage.getItem('selectedMaintenanceId')
    if (savedId) {
      selectedMaintenanceId.value = savedId
    }
    await loadMaintenanceList()
  }
})

onMounted(async () => {
  // 僅在已登入時載入資料
  if (!isAuthenticated.value) return

  // 從 localStorage 恢復之前的選擇
  const savedId = localStorage.getItem('selectedMaintenanceId')
  if (savedId) {
    selectedMaintenanceId.value = savedId
  }

  // 載入歲修列表
  await loadMaintenanceList()
})
</script>

<style>
.nav-link {
  @apply inline-flex items-center px-3 py-1.5 rounded text-sm font-medium text-slate-400 hover:text-cyan-300 hover:bg-cyan-500/10 transition-all duration-200;
}

.nav-link.active {
  @apply bg-cyan-500/15 text-cyan-400 shadow-sm shadow-cyan-500/20;
}

/* Logo 字母發光動畫 */
.logo-wrapper {
  position: relative;
  display: inline-block;
}

.logo-text {
  position: relative;
  z-index: 1;
}

.logo-glow {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 2;
  pointer-events: none;
  display: inline-flex;
}

.glow-letter {
  color: transparent;
  text-shadow:
    0 0 12px rgba(255, 255, 255, 1),
    0 0 28px rgba(255, 255, 255, 0.9),
    0 0 55px rgba(255, 255, 255, 0.6),
    0 0 90px rgba(250, 252, 255, 0.4);
  opacity: 0;
  animation: glow 20s ease-in-out infinite;
}

/* 動畫順序 N→E→T→O→R→A，純白核心 + 彩虹邊緣 */
.glow-1 {
  animation-delay: 0s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(255, 220, 220, 0.6),
    0 0 90px rgba(255, 100, 100, 0.35),
    0 0 120px rgba(255, 50, 50, 0.2);
}
.glow-2 {
  animation-delay: 0.3s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(255, 240, 200, 0.6),
    0 0 90px rgba(255, 180, 50, 0.35),
    0 0 120px rgba(255, 150, 0, 0.2);
}
.glow-3 {
  animation-delay: 0.6s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(220, 255, 220, 0.6),
    0 0 90px rgba(100, 255, 100, 0.35),
    0 0 120px rgba(0, 220, 100, 0.2);
}
.glow-4 {
  animation-delay: 0.9s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(200, 240, 255, 0.6),
    0 0 90px rgba(50, 200, 255, 0.35),
    0 0 120px rgba(0, 180, 255, 0.2);
}
.glow-5 {
  animation-delay: 1.2s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(220, 220, 255, 0.6),
    0 0 90px rgba(100, 100, 255, 0.35),
    0 0 120px rgba(80, 50, 255, 0.2);
}
.glow-6 {
  animation-delay: 1.5s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(255, 220, 255, 0.6),
    0 0 90px rgba(255, 100, 255, 0.35),
    0 0 120px rgba(220, 50, 255, 0.2);
}

@keyframes glow {
  0% {
    opacity: 0;
  }
  4% {
    opacity: 1;
  }
  10% {
    opacity: 0.75;
  }
  18%, 100% {
    opacity: 0;
  }
}
</style>
