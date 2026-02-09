<template>
  <div class="space-y-4">
    <!-- 標題列 -->
    <div class="flex justify-between items-center">
      <h1 class="text-xl font-bold text-white">系統日誌</h1>
      <div class="flex gap-2">
        <button
          @click="showCleanupModal = true"
          class="px-3 py-1.5 text-sm bg-red-600/20 text-red-400 border border-red-600/30 rounded hover:bg-red-600/30 transition"
        >
          清理舊日誌
        </button>
        <button
          @click="loadLogs"
          class="px-3 py-1.5 text-sm bg-cyan-600/20 text-cyan-400 border border-cyan-600/30 rounded hover:bg-cyan-600/30 transition"
        >
          重新整理
        </button>
      </div>
    </div>

    <!-- 統計卡片 -->
    <div class="grid grid-cols-4 gap-3">
      <div
        @click="filterByLevel('ERROR')"
        class="bg-slate-800 border rounded-lg p-3 text-center cursor-pointer transition hover:bg-slate-700/60"
        :class="filters.level === 'ERROR' ? 'border-red-500 ring-1 ring-red-500/40' : 'border-red-500/20'"
      >
        <div class="text-2xl font-bold text-red-400">{{ stats.error }}</div>
        <div class="text-xs text-slate-400 mt-1">ERROR</div>
      </div>
      <div
        @click="filterByLevel('WARNING')"
        class="bg-slate-800 border rounded-lg p-3 text-center cursor-pointer transition hover:bg-slate-700/60"
        :class="filters.level === 'WARNING' ? 'border-yellow-500 ring-1 ring-yellow-500/40' : 'border-yellow-500/20'"
      >
        <div class="text-2xl font-bold text-yellow-400">{{ stats.warning }}</div>
        <div class="text-xs text-slate-400 mt-1">WARNING</div>
      </div>
      <div
        @click="filterByLevel('INFO')"
        class="bg-slate-800 border rounded-lg p-3 text-center cursor-pointer transition hover:bg-slate-700/60"
        :class="filters.level === 'INFO' ? 'border-blue-500 ring-1 ring-blue-500/40' : 'border-blue-500/20'"
      >
        <div class="text-2xl font-bold text-blue-400">{{ stats.info }}</div>
        <div class="text-xs text-slate-400 mt-1">INFO</div>
      </div>
      <div
        @click="filterByLevel('')"
        class="bg-slate-800 border rounded-lg p-3 text-center cursor-pointer transition hover:bg-slate-700/60"
        :class="filters.level === '' ? 'border-slate-400 ring-1 ring-slate-400/40' : 'border-slate-600/30'"
      >
        <div class="text-2xl font-bold text-slate-300">{{ stats.total }}</div>
        <div class="text-xs text-slate-400 mt-1">全部</div>
      </div>
    </div>

    <!-- 過濾條件 -->
    <div class="bg-slate-800/50 border border-slate-700 rounded-lg p-3">
      <div class="flex flex-wrap gap-3 items-end">
        <div class="flex-1 min-w-[200px]">
          <label class="block text-xs text-slate-400 mb-1">搜尋</label>
          <input
            v-model="filters.search"
            type="text"
            placeholder="搜尋摘要、細節、模組..."
            class="w-full px-3 py-1.5 text-sm bg-slate-900 border border-slate-600 rounded text-white focus:outline-none focus:ring-1 focus:ring-cyan-400"
            @keyup.enter="loadLogs"
          />
        </div>
        <div>
          <label class="block text-xs text-slate-400 mb-1">等級</label>
          <select
            v-model="filters.level"
            class="px-3 py-1.5 text-sm bg-slate-900 border border-slate-600 rounded text-white focus:outline-none focus:ring-1 focus:ring-cyan-400"
          >
            <option value="">全部</option>
            <option value="ERROR">ERROR</option>
            <option value="WARNING">WARNING</option>
            <option value="INFO">INFO</option>
          </select>
        </div>
        <div>
          <label class="block text-xs text-slate-400 mb-1">來源</label>
          <select
            v-model="filters.source"
            class="px-3 py-1.5 text-sm bg-slate-900 border border-slate-600 rounded text-white focus:outline-none focus:ring-1 focus:ring-cyan-400"
          >
            <option value="">全部</option>
            <option value="api">API</option>
            <option value="scheduler">排程器</option>
            <option value="frontend">前端</option>
            <option value="service">服務</option>
          </select>
        </div>
        <div>
          <label class="block text-xs text-slate-400 mb-1">歲修</label>
          <select
            v-model="filters.maintenance_id"
            class="px-3 py-1.5 text-sm bg-slate-900 border border-slate-600 rounded text-white focus:outline-none focus:ring-1 focus:ring-cyan-400"
          >
            <option value="">全部</option>
            <option v-for="m in maintenanceList" :key="m.id" :value="m.id">
              {{ m.name && m.name !== m.id ? m.name : m.id }}
            </option>
          </select>
        </div>
        <button
          @click="loadLogs"
          class="px-4 py-1.5 text-sm bg-cyan-600 hover:bg-cyan-500 text-white rounded transition"
        >
          查詢
        </button>
        <button
          @click="resetFilters"
          class="px-4 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition"
        >
          重置
        </button>
      </div>
    </div>

    <!-- 日誌列表 -->
    <div class="bg-slate-800/50 border border-slate-700 rounded-lg overflow-hidden">
      <div v-if="loading" class="p-8 text-center text-slate-400">
        載入中...
      </div>
      <div v-else-if="logs.length === 0" class="p-8 text-center text-slate-500">
        沒有符合條件的日誌記錄
      </div>
      <table v-else class="min-w-full text-sm">
        <thead class="bg-slate-900/60">
          <tr>
            <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 w-36">時間</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 w-20">等級</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 w-20">來源</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-slate-400">摘要</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 w-16">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-700/50">
          <template v-for="log in logs" :key="log.id">
            <tr
              class="hover:bg-slate-700/30 transition cursor-pointer"
              @click="toggleDetail(log.id)"
            >
              <td class="px-3 py-2 text-slate-400 text-xs font-mono whitespace-nowrap">
                {{ formatTime(log.created_at) }}
              </td>
              <td class="px-3 py-2">
                <span
                  class="px-1.5 py-0.5 rounded text-xs font-medium"
                  :class="getLevelClass(log.level)"
                >
                  {{ log.level }}
                </span>
              </td>
              <td class="px-3 py-2 text-slate-300 text-xs">
                {{ getSourceLabel(log.source) }}
              </td>
              <td class="px-3 py-2 text-slate-200 truncate max-w-md" :title="log.summary">
                {{ log.summary }}
              </td>
              <td class="px-3 py-2">
                <button class="text-cyan-400 hover:text-cyan-300 text-xs">
                  {{ expandedIds.has(log.id) ? '收起' : '詳細' }}
                </button>
              </td>
            </tr>
            <!-- 展開的詳細資訊 -->
            <tr v-if="expandedIds.has(log.id)">
              <td colspan="5" class="px-4 py-3 bg-slate-900/50">
                <div class="space-y-2 text-xs">
                  <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <div v-if="log.module">
                      <span class="text-slate-500">模組:</span>
                      <span class="ml-1 text-slate-300">{{ log.module }}</span>
                    </div>
                    <div v-if="log.username">
                      <span class="text-slate-500">用戶:</span>
                      <span class="ml-1 text-slate-300">{{ log.username }}</span>
                    </div>
                    <div v-if="log.maintenance_id">
                      <span class="text-slate-500">歲修:</span>
                      <span class="ml-1 text-cyan-300 font-mono">{{ log.maintenance_id }}</span>
                    </div>
                    <div v-if="log.ip_address">
                      <span class="text-slate-500">IP:</span>
                      <span class="ml-1 text-slate-300 font-mono">{{ log.ip_address }}</span>
                    </div>
                    <div v-if="log.request_method">
                      <span class="text-slate-500">請求:</span>
                      <span class="ml-1 text-slate-300 font-mono">{{ log.request_method }} {{ log.request_path }}</span>
                    </div>
                    <div v-if="log.status_code">
                      <span class="text-slate-500">狀態碼:</span>
                      <span class="ml-1 text-slate-300">{{ log.status_code }}</span>
                    </div>
                  </div>
                  <div v-if="log.detail" class="mt-2">
                    <div class="text-slate-500 mb-1">詳細資訊:</div>
                    <pre class="bg-slate-950 border border-slate-700 rounded p-2 text-slate-300 overflow-x-auto max-h-60 whitespace-pre-wrap break-all">{{ log.detail }}</pre>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- 分頁 -->
    <div v-if="totalPages > 1" class="flex justify-between items-center text-sm">
      <div class="text-slate-400">
        共 {{ total }} 筆，第 {{ page }} / {{ totalPages }} 頁
      </div>
      <div class="flex gap-1">
        <button
          @click="goPage(page - 1)"
          :disabled="page <= 1"
          class="px-3 py-1 bg-slate-700 text-slate-300 rounded hover:bg-slate-600 transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          上一頁
        </button>
        <button
          v-for="p in visiblePages"
          :key="p"
          @click="goPage(p)"
          class="px-3 py-1 rounded transition"
          :class="p === page ? 'bg-cyan-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'"
        >
          {{ p }}
        </button>
        <button
          @click="goPage(page + 1)"
          :disabled="page >= totalPages"
          class="px-3 py-1 bg-slate-700 text-slate-300 rounded hover:bg-slate-600 transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          下一頁
        </button>
      </div>
    </div>

    <!-- 清理確認 Modal -->
    <div
      v-if="showCleanupModal"
      class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50"
      @click.self="showCleanupModal = false"
    >
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-2xl w-full max-w-sm p-5">
        <h3 class="text-lg font-bold text-white mb-4">清理舊日誌</h3>
        <div class="mb-4">
          <label class="block text-sm text-slate-400 mb-1">保留最近幾天的日誌？（0 = 全部刪除）</label>
          <input
            v-model.number="cleanupDays"
            type="number"
            min="0"
            max="365"
            class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
          />
        </div>
        <div class="flex justify-end gap-2">
          <button
            @click="showCleanupModal = false"
            class="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded transition"
          >
            取消
          </button>
          <button
            @click="doCleanup"
            class="px-4 py-2 bg-red-600 hover:bg-red-500 text-white text-sm rounded transition"
          >
            確認清理
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import { getAuthHeaders } from '@/utils/auth'

dayjs.extend(utc)

const loading = ref(false)
const logs = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const totalPages = ref(0)
const expandedIds = ref(new Set())
const stats = reactive({ error: 0, warning: 0, info: 0, total: 0 })
const showCleanupModal = ref(false)
const cleanupDays = ref(30)
const maintenanceList = ref([])

const filters = reactive({
  search: '',
  level: '',
  source: '',
  maintenance_id: '',
})

const visiblePages = computed(() => {
  const pages = []
  const start = Math.max(1, page.value - 2)
  const end = Math.min(totalPages.value, page.value + 2)
  for (let i = start; i <= end; i++) {
    pages.push(i)
  }
  return pages
})

function formatTime(isoStr) {
  if (!isoStr) return '-'
  return dayjs.utc(isoStr).local().format('MM-DD HH:mm:ss')
}

function getLevelClass(level) {
  switch (level) {
    case 'ERROR': return 'bg-red-900/50 text-red-400'
    case 'WARNING': return 'bg-yellow-900/50 text-yellow-400'
    case 'INFO': return 'bg-blue-900/50 text-blue-400'
    default: return 'bg-slate-700 text-slate-300'
  }
}

function getSourceLabel(source) {
  const labels = {
    api: 'API',
    scheduler: '排程器',
    frontend: '前端',
    service: '服務',
  }
  return labels[source] || source
}

function toggleDetail(id) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
  // 觸發響應式更新
  expandedIds.value = new Set(expandedIds.value)
}

async function loadLogs() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('page', page.value)
    params.set('page_size', pageSize)
    if (filters.level) params.set('level', filters.level)
    if (filters.source) params.set('source', filters.source)
    if (filters.search) params.set('search', filters.search)
    if (filters.maintenance_id) params.set('maintenance_id', filters.maintenance_id)

    const res = await fetch(`/api/v1/system-logs?${params}`, {
      headers: getAuthHeaders(),
    })
    if (res.ok) {
      const data = await res.json()
      logs.value = data.items
      total.value = data.total
      totalPages.value = data.total_pages
    }
  } catch (e) {
    console.error('載入日誌失敗:', e)
  } finally {
    loading.value = false
  }
  loadStats()
}

async function loadStats() {
  try {
    const res = await fetch('/api/v1/system-logs/stats', {
      headers: getAuthHeaders(),
    })
    if (res.ok) {
      const data = await res.json()
      stats.error = data.error
      stats.warning = data.warning
      stats.info = data.info
      stats.total = data.total
    }
  } catch (e) {
    console.error('載入統計失敗:', e)
  }
}

function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  loadLogs()
}

function filterByLevel(level) {
  filters.level = level
  page.value = 1
  loadLogs()
}

function resetFilters() {
  filters.search = ''
  filters.level = ''
  filters.source = ''
  filters.maintenance_id = ''
  page.value = 1
  loadLogs()
}

async function doCleanup() {
  try {
    const res = await fetch(`/api/v1/system-logs/cleanup?retain_days=${cleanupDays.value}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    })
    if (res.ok) {
      const data = await res.json()
      showCleanupModal.value = false
      alert(`已清理 ${data.deleted_count} 筆舊日誌`)
      loadLogs()
    }
  } catch (e) {
    console.error('清理日誌失敗:', e)
  }
}

async function loadMaintenanceList() {
  try {
    const res = await fetch('/api/v1/maintenance', {
      headers: getAuthHeaders(),
    })
    if (res.ok) {
      maintenanceList.value = await res.json()
    }
  } catch (e) {
    console.error('載入歲修列表失敗:', e)
  }
}

onMounted(() => {
  loadLogs()
  loadMaintenanceList()
})
</script>
