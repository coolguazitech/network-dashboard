<template>
  <div class="px-3 py-3">
    <!-- 頁面標題 + 摘要 + 餐點狀態 -->
    <div class="flex justify-between items-start mb-3">
      <div class="flex items-start gap-4">
        <div>
          <h1 class="text-xl font-bold text-white">指標總覽</h1>
        </div>
        <!-- 匯出報告按鈕 -->
        <div v-if="selectedMaintenanceId" class="relative">
          <button
            @click="showExportMenu = !showExportMenu"
            class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-sm font-medium transition flex items-center gap-1"
          >
            📄 匯出報告 <span class="text-xs">▼</span>
          </button>
          <!-- 下拉選單 -->
          <div
            v-if="showExportMenu"
            class="absolute left-0 mt-1 bg-slate-800 border border-slate-600 rounded-lg shadow-lg z-20 min-w-32"
          >
            <button
              @click="exportReport('preview')"
              class="w-full px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-700 hover:text-white transition"
            >
              👁️ 預覽
            </button>
            <button
              @click="exportReport('html')"
              class="w-full px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-700 hover:text-white transition"
            >
              📥 下載 HTML
            </button>
          </div>
        </div>
      </div>
      <!-- 整體通過率 -->
      <div class="text-right" v-if="selectedMaintenanceId">
        <div class="text-3xl font-black mb-0.5" :class="overallStatusColor">
          {{ overallPassRate }}%
        </div>
        <p class="text-xs text-slate-400">整體通過率</p>
      </div>
    </div>

    <!-- 整體進度條 -->
    <div v-if="selectedMaintenanceId" class="bg-slate-800/80 rounded border border-slate-600 p-3 mb-3">
      <div class="flex justify-between text-xs mb-1.5">
        <span class="text-slate-300 font-medium">驗收進度</span>
        <span class="text-slate-400">
          {{ summary.overall.pass_count }} / {{ summary.overall.total_count }} 項目通過
        </span>
      </div>
      <div class="w-full bg-slate-700 rounded-full h-2">
        <div
          class="h-2 rounded-full transition-all duration-500"
          :class="getProgressBarColor(summary.overall)"
          :style="{ width: summary.overall.pass_rate + '%' }"
        ></div>
      </div>
    </div>

    <!-- 指標卡片（按失敗數量排序） -->
    <div class="grid grid-cols-4 gap-2 mb-3">
      <div
        v-for="[type, indicator] in sortedIndicators"
        :key="type"
        @click="selectIndicator(type)"
        :class="[
          getCardBgColor(indicator),
          'rounded cursor-pointer transition overflow-hidden border hover:brightness-110',
          selectedIndicator === type ? 'border-cyan-500 ring-1 ring-cyan-500/50' : 'border-slate-600'
        ]"
      >
        <div class="px-3 py-2">
          <!-- 頂部：圖標 + 標題 -->
          <div class="flex justify-between items-center mb-1.5">
            <div class="flex items-center gap-1.5">
              <span class="text-lg">{{ getIcon(type) }}</span>
              <span class="text-white font-semibold text-sm">{{ getTitle(type) }}</span>
            </div>
            <span v-if="indicator.total_count === 0" class="text-xs px-1.5 py-0.5 bg-slate-700/50 text-slate-400 rounded font-medium">
              — 無資料
            </span>
            <span v-else-if="indicator.fail_count > 0" class="text-xs px-1.5 py-0.5 bg-red-900/50 text-red-400 rounded font-medium">
              {{ indicator.fail_count }} 失敗
            </span>
            <span v-else class="text-xs px-1.5 py-0.5 bg-green-900/50 text-green-400 rounded font-medium">
              ✓ 通過
            </span>
          </div>
          
          <!-- 通過率 -->
          <div class="flex items-end justify-between">
            <div class="text-2xl font-black" :class="getPassRateColor(indicator)">
              {{ indicator.total_count === 0 ? '—' : Math.round(indicator.pass_rate) + '%' }}
            </div>
            <div class="text-right text-xs text-slate-400">
              {{ indicator.pass_count }}/{{ indicator.total_count }}
            </div>
          </div>

          <!-- 迷你進度條（無資料時隱藏） -->
          <div v-if="indicator.total_count > 0" class="mt-1.5 w-full bg-slate-700 rounded-full h-1">
            <div
              class="h-1 rounded-full transition-all"
              :class="getProgressBarColor(indicator)"
              :style="{ width: indicator.pass_rate + '%' }"
            ></div>
          </div>
          <div v-else class="mt-1.5 h-1"></div>
        </div>
      </div>
    </div>

    <!-- 詳細失敗列表 -->
    <div class="bg-slate-800/80 rounded border border-slate-600 p-3">
      <div class="flex justify-between items-center mb-3">
        <h3 class="text-base font-bold text-white flex items-center gap-2">
          <span>{{ getIcon(selectedIndicator) }}</span>
          <span>{{ getTitle(selectedIndicator) }} - 詳細清單</span>
        </h3>
        <button
          @click="downloadCSV"
          :disabled="!indicatorDetails || !indicatorDetails.failures || indicatorDetails.failures.length === 0"
          class="px-2.5 py-1.5 bg-green-600 hover:bg-green-500 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed text-white rounded transition text-sm font-medium"
        >
          📥 匯出 CSV
        </button>
      </div>

      <!-- 失敗表格 -->
      <div v-if="indicatorDetails && indicatorDetails.failures && indicatorDetails.failures.length > 0" class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="bg-slate-900/60">
            <tr>
              <th class="px-4 py-2 text-left text-xs font-medium text-slate-400 uppercase">設備</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-slate-400 uppercase">
                {{ getColumnTitle(selectedIndicator) }}
              </th>
              <th class="px-4 py-2 text-left text-xs font-medium text-slate-400 uppercase">問題描述</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-700">
            <tr 
              v-for="(failure, idx) in indicatorDetails.failures" 
              :key="idx" 
              class="hover:bg-slate-700/50 transition"
            >
              <td class="px-4 py-2.5 whitespace-nowrap font-mono text-slate-200">
                {{ failure.device }}
              </td>
              <td class="px-4 py-2.5 whitespace-nowrap text-slate-300">
                {{ getInterfaceName(failure) }}
              </td>
              <td class="px-4 py-2.5 text-red-400">
                {{ failure.reason }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <!-- 無資料 -->
      <div v-else-if="!selectedIndicatorData || selectedIndicatorData.total_count === 0" class="text-center py-8 text-slate-400 bg-slate-900/40 rounded">
        <div class="text-4xl mb-2">📭</div>
        <p>尚無資料</p>
      </div>
      <!-- 全部通過 -->
      <div v-else class="text-center py-8 text-slate-400 bg-slate-900/40 rounded">
        <div class="text-4xl mb-2">✅</div>
        <p>無失敗項目 - 所有檢查都通過了！</p>
      </div>
    </div>

    <!-- 無數據提示 -->
    <div v-if="!selectedMaintenanceId" class="bg-slate-800/80 rounded border border-slate-600 p-8 text-center">
      <div class="text-5xl mb-3">📊</div>
      <p class="text-slate-400 text-lg">請先在頂部選擇歲修 ID</p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
      <div class="bg-slate-800 border border-slate-700 rounded-lg p-6">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400 mx-auto mb-2"></div>
        <p class="text-slate-300">載入中...</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject, watch, onUnmounted } from 'vue'
import axios from 'axios'
import { getAuthHeaders } from '../utils/auth.js'

const loading = ref(false)
const showExportMenu = ref(false)

// 點擊外部關閉選單
const handleClickOutside = (event) => {
  if (!event.target.closest('.relative')) {
    showExportMenu.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
const selectedMaintenanceId = inject('maintenanceId')
const summary = ref({
  maintenance_id: '',
  indicators: {},
  overall: {
    total_count: 0,
    pass_count: 0,
    fail_count: 0,
    pass_rate: 0.0,
  }
})

const selectedIndicator = ref('transceiver')
const indicatorDetails = ref(null)

// 取得當前選中指標的資料
const selectedIndicatorData = computed(() => {
  return summary.value.indicators[selectedIndicator.value] || null
})

const overallPassRate = computed(() => Math.round(summary.value.overall.pass_rate))

const overallStatusColor = computed(() => {
  const rate = summary.value.overall.pass_rate
  if (rate === 100) return 'text-green-400'
  if (rate >= 80) return 'text-yellow-400'
  return 'text-red-400'
})

const getTitle = (type) => {
  const titles = {
    transceiver: '光模塊驗收',
    version: '版本驗收',
    uplink: 'Uplink 驗收',
    port_channel: 'Port Channel 驗收',
    power: 'Power 驗收',
    fan: 'Fan 狀態驗收',
    error_count: 'Error Count 驗收',
    ping: 'Ping 連通性驗收',
  }
  return titles[type] || type
}

const getIcon = (type) => {
  const icons = {
    transceiver: '💡',      // Optical module - light
    version: '📦',          // Version - package
    uplink: '🔗',           // Uplink - link
    port_channel: '⛓️',     // Port Channel - chain
    power: '⚡',            // Power - lightning
    fan: '💨',              // Fan - wind
    error_count: '⚠️',     // Error - warning
    ping: '🌐',             // Ping - globe
  }
  return icons[type] || '📊'
}

// 判斷指標狀態類型
const getIndicatorStatus = (indicator) => {
  if (indicator.total_count === 0) return 'no-data'
  if (indicator.pass_rate === 100) return 'success'
  if (indicator.pass_rate >= 80) return 'warning'
  return 'error'
}

// 卡片背景色（淡色漸層）
const getCardBgColor = (indicator) => {
  const status = getIndicatorStatus(indicator)
  switch (status) {
    case 'no-data': return 'bg-slate-700/50'
    case 'success': return 'bg-green-900/30'
    case 'warning': return 'bg-yellow-900/20'
    case 'error': return 'bg-red-900/30'
    default: return 'bg-slate-800/80'
  }
}

// 通過率文字顏色
const getPassRateColor = (indicator) => {
  const status = getIndicatorStatus(indicator)
  switch (status) {
    case 'no-data': return 'text-slate-400'
    case 'success': return 'text-green-400'
    case 'warning': return 'text-yellow-400'
    case 'error': return 'text-red-400'
    default: return 'text-slate-400'
  }
}

// Progress Bar 顏色
const getProgressBarColor = (indicator) => {
  const status = getIndicatorStatus(indicator)
  switch (status) {
    case 'no-data': return 'bg-slate-600'
    case 'success': return 'bg-green-500'
    case 'warning': return 'bg-yellow-500'
    case 'error': return 'bg-red-500'
    default: return 'bg-slate-600'
  }
}

const getColumnTitle = (type) => {
  const titles = {
    transceiver: '接口',
    version: '設備',
    uplink: '鄰居',
    temperature: '感測器',
    fan: 'Fan ID',
  }
  return titles[type] || '項目'
}

const getInterfaceName = (failure) => {
  if (selectedIndicator.value === 'transceiver') {
    return failure.interface || '-'
  } else if (selectedIndicator.value === 'uplink') {
    return failure.expected_neighbor || '-'
  }
  return failure.device || '-'
}

// 獲取 Dashboard 摘要
const fetchSummary = async () => {
  if (!selectedMaintenanceId.value) return
  
  loading.value = true
  try {
    const response = await axios.get(`/api/v1/dashboard/maintenance/${selectedMaintenanceId.value}/summary`, {
      headers: getAuthHeaders()
    })
    summary.value = response.data
    
    // 默認選擇有失敗的指標
    for (const [type, data] of Object.entries(summary.value.indicators)) {
      if (data.fail_count > 0) {
        selectedIndicator.value = type
        break
      }
    }
    
    await fetchIndicatorDetails(selectedIndicator.value)
  } catch (error) {
    console.error('Failed to fetch summary:', error)
  } finally {
    loading.value = false
  }
}

// 獲取指標詳細數據
const fetchIndicatorDetails = async (type) => {
  if (!selectedMaintenanceId.value) return
  
  try {
    const response = await axios.get(
      `/api/v1/dashboard/maintenance/${selectedMaintenanceId.value}/indicator/${type}/details`,
      { headers: getAuthHeaders() }
    )
    indicatorDetails.value = response.data
  } catch (error) {
    console.error('Failed to fetch indicator details:', error)
    indicatorDetails.value = null
  }
}

// 選擇指標
const selectIndicator = async (type) => {
  selectedIndicator.value = type
  await fetchIndicatorDetails(type)
}

// 下載 CSV
const downloadCSV = () => {
  if (!indicatorDetails.value || !indicatorDetails.value.failures) return

  const failures = indicatorDetails.value.failures
  let csv = 'Device,Interface,Reason\n'

  failures.forEach(failure => {
    const device = failure.device || ''
    const interface_name = failure.interface || failure.expected_neighbor || ''
    const reason = (failure.reason || '').replace(/"/g, '""')
    csv += `"${device}","${interface_name}","${reason}"\n`
  })

  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  link.setAttribute('href', url)
  link.setAttribute('download', `${selectedIndicator.value}-failures.csv`)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

// 匯出報告
const exportReport = async (type) => {
  showExportMenu.value = false
  if (!selectedMaintenanceId.value) return

  if (type === 'preview') {
    // 開啟新視窗預覽
    window.open(`/api/v1/reports/maintenance/${selectedMaintenanceId.value}/export?include_details=true`, '_blank')
  } else if (type === 'html') {
    // 下載 HTML
    try {
      const response = await axios.get(
        `/api/v1/reports/maintenance/${selectedMaintenanceId.value}/export?include_details=true`,
        { responseType: 'blob', headers: getAuthHeaders() }
      )
      const blob = new Blob([response.data], { type: 'text/html;charset=utf-8' })
      const link = document.createElement('a')
      const url = URL.createObjectURL(blob)
      link.setAttribute('href', url)
      link.setAttribute('download', `sanity_report_${selectedMaintenanceId.value}.html`)
      link.style.visibility = 'hidden'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    } catch (error) {
      console.error('Failed to export report:', error)
    }
  }
}

// 排序後的指標（失敗的優先顯示）
const sortedIndicators = computed(() => {
  const indicators = Object.entries(summary.value.indicators)
  
  return indicators.sort((a, b) => {
    const [typeA, dataA] = a
    const [typeB, dataB] = b
    
    // 優先級：失敗數量多的在前
    if (dataA.fail_count !== dataB.fail_count) {
      return dataB.fail_count - dataA.fail_count
    }
    
    // 次要：通過率低的在前
    return dataA.pass_rate - dataB.pass_rate
  })
})

// 監聽全局 maintenance ID 變化
watch(selectedMaintenanceId, (newId) => {
  if (newId) {
    fetchSummary()
  }
})

onMounted(() => {
  if (selectedMaintenanceId.value) {
    fetchSummary()
  }
})
</script>
