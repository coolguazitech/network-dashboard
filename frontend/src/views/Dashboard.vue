<template>
  <div class="space-y-4">
    <!-- 上方：維護作業摘要 -->
    <div class="bg-white rounded shadow p-4">
      <div class="flex justify-between items-start">
        <div>
          <h2 class="text-xl font-bold text-gray-800 mb-1">
            2026年Q1歲修作業
          </h2>
          <p class="text-sm text-gray-600">
            維護作業 ID: <span class="font-mono">2026Q1-ANNUAL</span>
          </p>
          <p class="text-sm text-gray-600">
            期間: 2026-01-15 ~ 2026-01-31
          </p>
        </div>
        <div class="text-right">
          <div class="text-3xl font-bold mb-1" :class="overallStatusColor">
            {{ overallPassRate }}%
          </div>
          <p class="text-sm text-gray-600">整體通過率</p>
        </div>
      </div>

      <!-- 進度條 -->
      <div class="mt-4">
        <div class="flex justify-between text-xs mb-2">
          <span class="text-gray-700">驗收進度</span>
          <span class="text-gray-600">
            {{ summary.overall.pass_count }} / {{ summary.overall.total_count }}
          </span>
        </div>
        <div class="w-full bg-gray-200 rounded-full h-2">
          <div
            class="bg-blue-600 h-2 rounded-full transition-all duration-500"
            :style="{ width: summary.overall.pass_rate + '%' }"
          ></div>
        </div>
      </div>
    </div>

    <!-- 中間：指標卡片（按失敗數量排序） -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
      <IndicatorPie
        v-for="[type, indicator] in sortedIndicators"
        :key="type"
        :type="type"
        :data="indicator"
        :is-selected="selectedIndicator === type"
        @click="selectIndicator(type)"
      />
    </div>

    <!-- 下方：詳細表格 -->
    <div class="bg-white rounded-lg shadow p-6">
      <div class="flex justify-between items-center mb-6">
        <h3 class="text-xl font-bold text-gray-800">
          {{ getTitle(selectedIndicator) }} - 詳細清單
        </h3>
        <button
          @click="downloadCSV"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
        >
          📥 下載 CSV
        </button>
      </div>

      <!-- 失敗表格 -->
      <div v-if="indicatorDetails && indicatorDetails.failures && indicatorDetails.failures.length > 0">
        <div class="overflow-x-auto">
          <table class="min-w-full">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">設備</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">
                  {{ getColumnTitle(selectedIndicator) }}
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">問題描述</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">
              <tr v-for="(failure, idx) in indicatorDetails.failures" :key="idx" class="hover:bg-gray-50">
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {{ failure.device }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                  {{ getInterfaceName(failure) }}
                </td>
                <td class="px-6 py-4 text-sm text-red-600">
                  {{ failure.reason }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else class="text-center py-8 text-gray-500">
        ✅ 無失敗項目 - 所有檢查都通過了！
      </div>
    </div>

    <!-- 加載狀態 -->
    <div v-if="loading" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-8">
        <p class="text-gray-700">加載中...</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import IndicatorPie from '../components/IndicatorPie.vue'

const loading = ref(false)
const summary = ref({
  maintenance_id: '2026Q1-ANNUAL',
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

const overallPassRate = computed(() => Math.round(summary.value.overall.pass_rate))

const overallStatusColor = computed(() => {
  const rate = summary.value.overall.pass_rate
  if (rate === 100) return 'text-green-600'
  if (rate >= 80) return 'text-yellow-600'
  return 'text-red-600'
})

const getTitle = (type) => {
  const titles = {
    transceiver: '光模塊驗收',
    version: '版本驗收',
    uplink: 'Uplink 驗收',
  }
  return titles[type] || type
}

const getIcon = (type) => {
  const icons = {
    transceiver: '🔌',
    version: '📦',
    uplink: '🔗',
  }
  return icons[type] || '📊'
}

const getPassRateColor = (rate) => {
  if (rate === 100) return 'text-green-600'
  if (rate >= 80) return 'text-yellow-600'
  return 'text-red-600'
}

const getColumnTitle = (type) => {
  const titles = {
    transceiver: '接口',
    version: '設備',
    uplink: '鄰居',
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
  loading.value = true
  try {
    const response = await axios.get('/api/v1/dashboard/maintenance/2026Q1-ANNUAL/summary')
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
  try {
    const response = await axios.get(
      `/api/v1/dashboard/maintenance/2026Q1-ANNUAL/indicator/${type}/details`
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
  
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  link.setAttribute('href', url)
  link.setAttribute('download', `${selectedIndicator.value}-failures.csv`)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
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

onMounted(() => {
  fetchSummary()
})
</script>
