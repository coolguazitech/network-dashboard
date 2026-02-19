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
          <Transition name="dropdown">
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
          </Transition>
        </div>
      </div>
      <!-- 整體通過率 -->
      <div class="text-right" v-if="selectedMaintenanceId">
        <div class="text-3xl font-black mb-0.5 tabular-nums" :class="overallStatusColor">
          {{ animatedOverallRate }}%
        </div>
        <p class="text-xs text-slate-400">整體通過率</p>
      </div>
    </div>

    <!-- 整體進度條 -->
    <div v-if="selectedMaintenanceId" class="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/30 p-3 mb-3 shadow-sm">
      <div class="flex justify-between text-xs mb-1.5">
        <span class="text-slate-300 font-medium">驗收進度</span>
        <span class="text-slate-400 tabular-nums">
          {{ animatedPassCount }} / {{ animatedTotalCount }} 項目通過
        </span>
      </div>
      <div class="w-full bg-slate-700/50 rounded-full h-2.5 overflow-hidden">
        <div
          class="h-2.5 rounded-full bar-animate"
          :class="getProgressBarColor(summary.overall)"
          :style="{ width: summary.overall.pass_rate + '%' }"
          style="box-shadow: 0 0 12px rgba(0, 210, 255, 0.2)"
        ></div>
      </div>
    </div>

    <!-- 指標卡片 -->
    <div class="grid grid-cols-4 gap-2 mb-3">
      <div
        v-for="([type, indicator], idx) in sortedIndicators"
        :key="type"
        @click="selectIndicator(type)"
        class="card-stagger"
        :style="{ animationDelay: idx * 80 + 'ms' }"
        :class="[
          getCardBgColor(indicator),
          'rounded-xl cursor-pointer transition-all duration-200 border hover:brightness-110 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/15',
          selectedIndicator === type ? 'border-cyan-500/60 ring-1 ring-cyan-500/30 shadow-lg shadow-cyan-500/10' : 'border-slate-600/40'
        ]"
      >
        <div class="px-3 py-2">
          <!-- 頂部：圖標 + 標題 + 閾值設定 -->
          <div class="flex justify-between items-center mb-1.5">
            <div class="flex items-center gap-1.5">
              <span class="text-lg">{{ getIcon(type) }}</span>
              <span class="text-white font-semibold text-sm">{{ getTitle(type) }}</span>
              <!-- 指標說明 tooltip -->
              <div class="relative group/info" @click.stop>
                <svg class="w-3.5 h-3.5 text-slate-500 group-hover/info:text-amber-400 transition cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div class="absolute left-0 bottom-full mb-2 w-80 px-3.5 py-2.5 bg-amber-50 border border-amber-300 rounded-lg shadow-lg text-xs text-amber-900 leading-relaxed opacity-0 invisible group-hover/info:opacity-100 group-hover/info:visible transition-all duration-200 z-50 pointer-events-none"
                  style="filter: drop-shadow(0 2px 8px rgba(217, 160, 0, 0.2));"
                >
                  {{ getDescription(type) }}
                  <div class="absolute left-4 top-full w-0 h-0 border-l-[6px] border-r-[6px] border-t-[6px] border-transparent border-t-amber-300"></div>
                  <div class="absolute left-4 top-full -mt-px w-0 h-0 border-l-[6px] border-r-[6px] border-t-[6px] border-transparent border-t-amber-50"></div>
                </div>
              </div>
              <button
                v-if="hasThresholdConfig(type) && canWrite"
                @click.stop="openThresholdModal(type)"
                class="text-slate-500 hover:text-cyan-400 transition p-0.5"
                title="閾值設定"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </button>
            </div>
            <span v-if="indicator.fail_count > 0 && indicator.collection_errors > 0" class="text-xs px-1.5 py-0.5 bg-purple-900/50 text-purple-400 rounded font-medium">
              {{ indicator.fail_count }} 未通過 ({{ indicator.collection_errors }} 異常)
            </span>
            <span v-else-if="indicator.total_count === 0" class="text-xs px-1.5 py-0.5 bg-slate-700/50 text-slate-400 rounded font-medium">
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
              {{ indicator.total_count === 0 ? '—' : Math.floor(indicator.pass_rate) + '%' }}
            </div>
            <div class="text-right text-xs text-slate-400">
              {{ indicator.pass_count }}/{{ indicator.total_count }}
            </div>
          </div>

          <!-- 迷你進度條（無資料時隱藏） -->
          <div v-if="indicator.total_count > 0" class="mt-1.5 w-full bg-slate-700 rounded-full h-1 overflow-hidden">
            <div
              class="h-1 rounded-full bar-animate"
              :class="getProgressBarColor(indicator)"
              :style="{ width: indicator.pass_rate + '%', animationDelay: (idx * 80 + 200) + 'ms' }"
            ></div>
          </div>
          <div v-else class="mt-1.5 h-1"></div>
        </div>
      </div>
    </div>

    <!-- 詳細清單 -->
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

      <!-- 無資料 -->
      <div v-if="!selectedIndicatorData || selectedIndicatorData.total_count === 0" class="text-center py-8 text-slate-400 bg-slate-900/40 rounded">
        <div class="text-4xl mb-2">📭</div>
        <p>尚無資料</p>
      </div>

      <template v-else-if="indicatorDetails">
        <!-- 失敗表格 -->
        <div v-if="indicatorDetails.failures && indicatorDetails.failures.length > 0" class="overflow-x-auto mb-3">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-red-400 font-semibold text-sm">❌ 未通過項目 ({{ indicatorDetails.failures.length }})</span>
          </div>
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
                <td class="px-4 py-2.5" :class="failure.is_system_error ? 'text-purple-400' : 'text-red-400'">
                  {{ failure.reason }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 通過項目表格 -->
        <div v-if="indicatorDetails.passes && indicatorDetails.passes.length > 0" class="overflow-x-auto">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-green-400 font-semibold text-sm">✅ 通過項目 (前 {{ indicatorDetails.passes.length }} 筆，共 {{ indicatorDetails.pass_count }} 筆通過)</span>
          </div>
          <table class="min-w-full text-sm">
            <thead class="bg-slate-900/60">
              <tr>
                <th class="px-4 py-2 text-left text-xs font-medium text-slate-400 uppercase">設備</th>
                <th class="px-4 py-2 text-left text-xs font-medium text-slate-400 uppercase">
                  {{ getColumnTitle(selectedIndicator) }}
                </th>
                <th class="px-4 py-2 text-left text-xs font-medium text-slate-400 uppercase">通過描述</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-700">
              <tr
                v-for="(pass_item, idx) in indicatorDetails.passes"
                :key="'pass-' + idx"
                class="hover:bg-slate-700/50 transition"
              >
                <td class="px-4 py-2.5 whitespace-nowrap font-mono text-slate-200">
                  {{ pass_item.device }}
                </td>
                <td class="px-4 py-2.5 whitespace-nowrap text-slate-300">
                  {{ getInterfaceName(pass_item) }}
                </td>
                <td class="px-4 py-2.5 text-green-400">
                  {{ pass_item.reason }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 全部通過但無 passes 細節 -->
        <div v-if="(!indicatorDetails.failures || indicatorDetails.failures.length === 0) && (!indicatorDetails.passes || indicatorDetails.passes.length === 0)" class="text-center py-8 text-slate-400 bg-slate-900/40 rounded">
          <div class="text-4xl mb-2">✅</div>
          <p>無失敗項目 - 所有檢查都通過了！</p>
        </div>
      </template>
    </div>

    <!-- 無數據提示 -->
    <div v-if="!selectedMaintenanceId" class="bg-slate-800/80 rounded border border-slate-600 p-8 text-center">
      <div class="text-5xl mb-3">📊</div>
      <p class="text-slate-400 text-lg">請先在頂部選擇歲修 ID</p>
    </div>

    <!-- 閾值設定 Modal -->
    <Transition name="modal">
    <div v-if="showThresholdModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="showThresholdModal = false">
      <div class="modal-content bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl p-5 w-full max-w-lg max-h-[80vh] overflow-y-auto shadow-2xl shadow-black/30">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-white">
            {{ getIcon(thresholdModalType) }} {{ getTitle(thresholdModalType) }} - 閾值設定
          </h3>
          <button @click="showThresholdModal = false" class="text-slate-400 hover:text-white transition text-xl">&times;</button>
        </div>

        <!-- Transceiver 閾值 -->
        <template v-if="thresholdModalType === 'transceiver'">
          <div v-for="field in transceiverFields" :key="field.key" class="mb-3">
            <div class="flex items-center gap-2 mb-1">
              <label class="text-sm text-slate-300 font-medium">{{ field.label }}</label>
              <span class="text-xs text-slate-500">({{ field.unit }})</span>
              <span v-if="isOverride(field.key)" class="text-xs px-1.5 py-0.5 bg-cyan-900/50 text-cyan-400 rounded">已覆寫</span>
            </div>
            <div class="flex items-center gap-2">
              <input
                type="number"
                step="0.1"
                v-model.number="thresholdForm[field.key]"
                :placeholder="'預設: ' + getDefaultValue(field.key)"
                class="flex-1 px-3 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm text-white focus:ring-1 focus:ring-cyan-400 focus:border-cyan-400 outline-none"
              />
              <button
                v-if="thresholdForm[field.key] !== null && thresholdForm[field.key] !== ''"
                @click="thresholdForm[field.key] = null"
                class="text-xs text-slate-400 hover:text-red-400 transition whitespace-nowrap"
                title="恢復預設"
              >
                清除
              </button>
            </div>
          </div>
        </template>

        <!-- 操作按鈕 -->
        <div class="flex justify-between items-center mt-5 pt-4 border-t border-slate-700">
          <button
            @click="resetThresholds"
            class="px-3 py-1.5 text-sm text-slate-400 hover:text-red-400 transition"
          >
            全部恢復預設
          </button>
          <div class="flex gap-2">
            <button
              @click="showThresholdModal = false"
              class="px-4 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded text-sm transition"
            >
              取消
            </button>
            <button
              @click="saveThresholds"
              :disabled="savingThresholds"
              class="px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded text-sm font-medium transition"
            >
              {{ savingThresholds ? '儲存中...' : '儲存' }}
            </button>
          </div>
        </div>
      </div>
    </div>
    </Transition>

    <!-- Loading -->
    <Transition name="modal">
    <div v-if="loading" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
      <div class="modal-content bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl p-6 shadow-2xl shadow-black/30">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400 mx-auto mb-2"></div>
        <p class="text-slate-300">載入中...</p>
      </div>
    </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject, watch, onUnmounted } from 'vue'
import api, { downloadFile } from '@/utils/api'
import { canWrite } from '@/utils/auth'
import { useAnimatedNumber } from '@/composables/useAnimatedNumber'

const loading = ref(false)
const showExportMenu = ref(false)

// ── 閾值設定 ──
const showThresholdModal = ref(false)
const thresholdModalType = ref('')
const thresholdData = ref(null)
const thresholdForm = ref({})
const savingThresholds = ref(false)

const transceiverFields = [
  { key: 'transceiver_tx_power_min', label: 'TX Power 下限', unit: 'dBm' },
  { key: 'transceiver_tx_power_max', label: 'TX Power 上限', unit: 'dBm' },
  { key: 'transceiver_rx_power_min', label: 'RX Power 下限', unit: 'dBm' },
  { key: 'transceiver_rx_power_max', label: 'RX Power 上限', unit: 'dBm' },
  { key: 'transceiver_temperature_min', label: '溫度下限', unit: '°C' },
  { key: 'transceiver_temperature_max', label: '溫度上限', unit: '°C' },
  { key: 'transceiver_voltage_min', label: '電壓下限', unit: 'V' },
  { key: 'transceiver_voltage_max', label: '電壓上限', unit: 'V' },
]

const hasThresholdConfig = (type) => type === 'transceiver'

const getDefaultValue = (key) => {
  if (!thresholdData.value) return ''
  // 從分組結構中找到對應的 default
  for (const group of Object.values(thresholdData.value)) {
    for (const [shortKey, info] of Object.entries(group)) {
      // 比對完整 key（group_name + short_key）
      const groupName = Object.keys(thresholdData.value).find(g => thresholdData.value[g] === group)
      if (`${groupName}_${shortKey}` === key) return info.default
    }
  }
  return ''
}

const isOverride = (key) => {
  if (!thresholdData.value) return false
  for (const group of Object.values(thresholdData.value)) {
    for (const [shortKey, info] of Object.entries(group)) {
      const groupName = Object.keys(thresholdData.value).find(g => thresholdData.value[g] === group)
      if (`${groupName}_${shortKey}` === key) return info.is_override
    }
  }
  return false
}

const fetchThresholds = async () => {
  if (!selectedMaintenanceId.value) return
  try {
    const response = await api.get(`/thresholds/${selectedMaintenanceId.value}`)
    thresholdData.value = response.data
  } catch (error) {
    console.error('Failed to fetch thresholds:', error)
  }
}

const openThresholdModal = async (type) => {
  thresholdModalType.value = type
  await fetchThresholds()

  // 用目前的 value 填充表單
  const form = {}
  if (thresholdData.value) {
    const groupData = thresholdData.value[type]
    if (groupData) {
      for (const [shortKey, info] of Object.entries(groupData)) {
        const fullKey = `${type}_${shortKey}`
        form[fullKey] = info.is_override ? info.value : null
      }
    }
  }
  thresholdForm.value = form
  showThresholdModal.value = true
}

const saveThresholds = async () => {
  savingThresholds.value = true
  try {
    const updates = {}
    for (const [key, value] of Object.entries(thresholdForm.value)) {
      // 傳 null 清除覆寫，傳數值設定覆寫
      updates[key] = (value === null || value === '') ? null : Number(value)
    }
    const response = await api.put(`/thresholds/${selectedMaintenanceId.value}`, updates)
    thresholdData.value = response.data
    showThresholdModal.value = false
    // 重新載入 Dashboard 資料
    await fetchSummary()
  } catch (error) {
    console.error('Failed to save thresholds:', error)
  } finally {
    savingThresholds.value = false
  }
}

const resetThresholds = async () => {
  savingThresholds.value = true
  try {
    // 只重置當前指標群組：將 form 中所有欄位設為 null → PUT 清除覆寫
    const updates = {}
    for (const key of Object.keys(thresholdForm.value)) {
      updates[key] = null
    }
    const response = await api.put(`/thresholds/${selectedMaintenanceId.value}`, updates)
    thresholdData.value = response.data
    // 重新填充表單為預設值（不關閉 modal）
    const form = {}
    const groupData = thresholdData.value[thresholdModalType.value]
    if (groupData) {
      for (const [shortKey, info] of Object.entries(groupData)) {
        form[`${thresholdModalType.value}_${shortKey}`] = info.is_override ? info.value : null
      }
    }
    thresholdForm.value = form
    await fetchSummary()
  } catch (error) {
    console.error('Failed to reset thresholds:', error)
  } finally {
    savingThresholds.value = false
  }
}

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

const overallPassRate = computed(() => Math.floor(summary.value.overall.pass_rate))
const { displayed: animatedOverallRate } = useAnimatedNumber(overallPassRate)
const overallPassCount = computed(() => summary.value.overall.pass_count)
const overallTotalCount = computed(() => summary.value.overall.total_count)
const { displayed: animatedPassCount } = useAnimatedNumber(overallPassCount)
const { displayed: animatedTotalCount } = useAnimatedNumber(overallTotalCount)

// 整體狀態顏色（後端計算 status）
const _overallStatusColors = { success: 'text-green-400', warning: 'text-yellow-400', error: 'text-red-400' }
const overallStatusColor = computed(() => _overallStatusColors[summary.value.overall.status] || 'text-slate-400')

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

const getDescription = (type) => {
  const descriptions = {
    transceiver: '每個光模塊的 TX Power、RX Power、溫度、電壓皆須落在閾值範圍內：MIN ≤ 數值 ≤ MAX。四項全部合格才算通過，任一超標即失敗。📍 閾值可點擊本卡片標題旁的齒輪圖示自訂。',
    version: '比對新設備的實際韌體版本是否符合預期版本清單（可設定多個）。actual_version ∈ {expected_versions} → 通過。📍 至「設定 → 版本期望」匯入或新增預期版本。',
    uplink: '透過 CDP/LLDP 鄰居資訊，逐一比對每台設備的實際鄰居是否包含預期鄰居。expected_neighbor ∈ actual_neighbors → 通過。📍 至「設定 → Uplink 期望」匯入或新增預期鄰居。',
    port_channel: '檢查四項條件：① Port-Channel 存在 ② 狀態為 UP ③ 所有預期成員埠皆存在 ④ 各成員埠狀態為 UP/Bundled。四項全過才算通過。📍 至「設定 → Port Channel 期望」匯入或新增。',
    power: '檢查每台設備的所有 PSU 狀態是否為健康值（如 Normal / OK）。任一 PSU 異常 → 該設備失敗。通過率 = 全部 PSU 正常的設備數 ÷ 總設備數 × 100%。📍 自動採集，無需額外設定。',
    fan: '檢查每台設備的所有風扇狀態是否為健康值（如 Normal / OK）。任一風扇異常 → 該設備失敗。通過率 = 全部風扇正常的設備數 ÷ 總設備數 × 100%。📍 自動採集，無需額外設定。',
    error_count: '比較前後兩次採集的 CRC/FCS 錯誤計數差值：delta = 本次 − 上次。delta > 0 → 失敗（錯誤增長）；delta ≤ 0 → 通過。首次採集無歷史資料則自動通過。📍 自動採集，無需額外設定。',
    ping: '對新設備管理 IP 發送 ICMP Ping。is_reachable = true → 通過；false → 失敗。通過率 = 可達設備數 ÷ 總新設備數 × 100%。📍 設備清單於「設備管理 → 設備清單」設定。',
  }
  return descriptions[type] || ''
}

// 指標狀態 → 視覺映射（status 由後端計算）
const _cardBgColors = {
  'system-error': 'bg-purple-900/30', 'no-data': 'bg-slate-700/50',
  'success': 'bg-green-900/30', 'warning': 'bg-yellow-900/20', 'error': 'bg-red-900/30',
}
const _passRateColors = {
  'system-error': 'text-purple-400', 'no-data': 'text-slate-400',
  'success': 'text-green-400', 'warning': 'text-yellow-400', 'error': 'text-red-400',
}
const _progressBarColors = {
  'system-error': 'bg-purple-500', 'no-data': 'bg-slate-600',
  'success': 'bg-green-500', 'warning': 'bg-yellow-500', 'error': 'bg-red-500',
}

const getIndicatorStatus = (indicator) => indicator.status || 'no-data'
const getCardBgColor = (indicator) => _cardBgColors[indicator.status] || 'bg-slate-800/80'
const getPassRateColor = (indicator) => _passRateColors[indicator.status] || 'text-slate-400'
const getProgressBarColor = (indicator) => _progressBarColors[indicator.status] || 'bg-slate-600'

const getColumnTitle = (type) => {
  const titles = {
    transceiver: '接口',
    version: '設備',
    uplink: '鄰居',
    port_channel: 'Port-Channel',
    power: 'PSU',
    fan: 'Fan ID',
    error_count: '接口',
    ping: '管理 IP',
  }
  return titles[type] || '項目'
}

const getInterfaceName = (item) => {
  if (!item) return '-'
  if (selectedIndicator.value === 'transceiver') return item.interface || '-'
  if (selectedIndicator.value === 'uplink') return item.expected_neighbor || '-'
  if (selectedIndicator.value === 'port_channel') return item.interface || '-'
  if (selectedIndicator.value === 'error_count') return item.interface || '-'
  if (selectedIndicator.value === 'ping') return item.interface || '-'
  return item.interface || item.device || '-'
}

// 獲取 Dashboard 摘要
const fetchSummary = async () => {
  if (!selectedMaintenanceId.value) return
  
  loading.value = true
  try {
    const response = await api.get(`/dashboard/maintenance/${selectedMaintenanceId.value}/summary`)
    summary.value = response.data
    
    // 默認選擇有系統異常或失敗的指標
    for (const [type, data] of Object.entries(summary.value.indicators)) {
      if ((data.collection_errors || 0) > 0 || data.fail_count > 0) {
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
    const response = await api.get(
      `/dashboard/maintenance/${selectedMaintenanceId.value}/indicator/${type}/details`
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
    // 透過 axios（含 auth）取得 HTML，再以 blob URL 開啟新視窗
    try {
      const response = await api.get(
        `/reports/maintenance/${selectedMaintenanceId.value}/export?include_details=true`,
        { responseType: 'blob' }
      )
      const blob = new Blob([response.data], { type: 'text/html;charset=utf-8' })
      const blobUrl = URL.createObjectURL(blob)
      window.open(blobUrl, '_blank')
    } catch (error) {
      console.error('Failed to preview report:', error)
    }
  } else if (type === 'html') {
    // 下載 HTML
    try {
      const response = await api.get(
        `/reports/maintenance/${selectedMaintenanceId.value}/export?include_details=true`,
        { responseType: 'blob' }
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

// 指標列表（固定順序，與後端回傳一致）
const sortedIndicators = computed(() => {
  return Object.entries(summary.value.indicators)
})

// ── 自動刷新（每 30 秒） ──
let pollTimer = null

const startPolling = () => {
  stopPolling()
  if (!selectedMaintenanceId.value) return
  pollTimer = setInterval(() => {
    // 靜默刷新：不設 loading，避免閃爍
    fetchSummary()
  }, 30000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 監聽全局 maintenance ID 變化
watch(selectedMaintenanceId, (newId) => {
  stopPolling()
  if (newId) {
    fetchSummary()
    startPolling()
  }
})

onMounted(() => {
  if (selectedMaintenanceId.value) {
    fetchSummary()
    startPolling()
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>
