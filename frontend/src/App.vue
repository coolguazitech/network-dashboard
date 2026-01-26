<template>
  <div class="min-h-screen bg-slate-900">
    <!-- 頂部導航 -->
    <nav class="bg-slate-800 border-b border-slate-700">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-16">
          <div class="flex">
            <div class="flex-shrink-0 flex items-center">
              <h1 class="text-xl font-bold text-slate-100">
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
                to="/comparison"
                class="nav-link"
                :class="{ active: $route.path === '/comparison' }"
              >
                Compare
              </router-link>
              <router-link
                to="/devices"
                class="nav-link"
                :class="{ active: $route.path === '/devices' }"
              >
                Devices
              </router-link>
              <router-link
                to="/settings"
                class="nav-link"
                :class="{ active: $route.path === '/settings' }"
              >
                Settings
              </router-link>
            </div>
          </div>
          <div class="flex items-center space-x-4">
            <!-- 全局 Maintenance ID 選擇器 -->
            <div class="flex items-center space-x-2">
              <label class="text-xs font-medium text-slate-400">歲修 ID:</label>
              <select
                v-model="selectedMaintenanceId"
                @change="onMaintenanceIdChange"
                class="px-3 py-1 text-sm bg-slate-700 border border-slate-600 text-slate-200 rounded focus:outline-none focus:ring-2 focus:ring-cyan-500"
              >
                <option value="">-- 請選擇 --</option>
                <option 
                  v-for="m in maintenanceList" 
                  :key="m.id" 
                  :value="m.id"
                >
                  {{ m.id }}{{ m.name ? ` (${m.name})` : '' }}
                </option>
              </select>
              <button 
                @click="showMaintenanceModal = true"
                class="text-cyan-400 hover:text-cyan-300 text-sm px-2 py-1 border border-cyan-600 rounded hover:bg-cyan-900/30 transition"
                title="管理歲修"
              >
                ⚙️ 管理
              </button>
            </div>
            <span class="text-sm text-slate-500">
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
              <td colspan="4" class="px-3 py-6 text-center text-slate-500">尚無歲修記錄</td>
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
import { ref, onMounted, provide } from 'vue'
import dayjs from 'dayjs'

const lastUpdate = ref('--')
const selectedMaintenanceId = ref('')
const maintenanceList = ref([])

// 歲修管理 Modal
const showMaintenanceModal = ref(false)
const newMaintenance = ref({ id: '', name: '' })

// 刪除確認 Modal
const showDeleteModal = ref(false)
const deleteTarget = ref(null)
const deleteConfirmInput = ref('')

const updateTime = () => {
  lastUpdate.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return dayjs(dateStr).format('YYYY-MM-DD HH:mm')
}

const loadMaintenanceList = async () => {
  try {
    const res = await fetch('/api/v1/maintenance')
    if (res.ok) {
      maintenanceList.value = await res.json()
      
      // 如果當前選中的不在列表中，重置選擇
      if (selectedMaintenanceId.value) {
        const found = maintenanceList.value.find(m => m.id === selectedMaintenanceId.value)
        if (!found && maintenanceList.value.length > 0) {
          selectedMaintenanceId.value = maintenanceList.value[0].id
          onMaintenanceIdChange()
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
      headers: { 'Content-Type': 'application/json' },
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

onMounted(async () => {
  updateTime()
  setInterval(updateTime, 60000)
  
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
  @apply inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors;
}

.nav-link.active {
  @apply border-cyan-500 text-slate-100;
}
</style>
