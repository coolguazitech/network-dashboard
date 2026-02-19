<template>
  <div class="meal-sidebar">
    <div class="meal-container">
      <div class="title">便當</div>
      <div class="bento-icon">🍱</div>
      <div
        v-for="(zone, zi) in zones"
        :key="zone.zone_code"
        class="zone-item field-stagger"
        :style="{ animationDelay: zi * 100 + 'ms' }"
        :title="getTooltip(zone)"
      >
        <div
          class="light"
          :class="getLightClass(zone)"
          @click="toggleStatus(zone)"
        >
          <span v-if="zone.status === 'arrived'" class="arrived-icon">✓</span>
        </div>
        <span class="zone-label">{{ zone.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, inject, watch } from 'vue'
import api from '@/utils/api'
import { canWrite } from '@/utils/auth'

const maintenanceId = inject('maintenanceId')

// 定時輪詢間隔 (毫秒) - 每 10 秒更新一次
const POLL_INTERVAL = 10000
let pollTimer = null

const zones = ref([
  { zone_code: 'HSP', label: '竹', status: 'no_meal' },
  { zone_code: 'CSP', label: '中', status: 'no_meal' },
  { zone_code: 'SSP', label: '南', status: 'no_meal' },
])

const getLightClass = (zone) => ({
  'light-gray': zone.status === 'no_meal',
  'light-red': zone.status === 'pending',
  'light-green': zone.status === 'arrived',
  'light-readonly': !canWrite.value,
  'pulse-pending': zone.status === 'pending',
})

const getTooltip = (zone) => {
  const names = { HSP: '竹科', CSP: '中科', SSP: '南科' }
  const statusText = { no_meal: '無便當', pending: '等待中', arrived: '已送達' }
  return `${names[zone.zone_code]}：${statusText[zone.status]}`
}

// 統一轉小寫（後端 enum 為大寫，前端 CSS class 用小寫）
const normalizeStatus = (s) => (s || 'no_meal').toLowerCase()

const toggleStatus = (zone) => {
  // Guest 無法切換狀態
  if (!canWrite.value) return

  const order = ['no_meal', 'pending', 'arrived']
  const prevStatus = zone.status
  const nextStatus = order[(order.indexOf(prevStatus) + 1) % 3]

  const idx = zones.value.findIndex(z => z.zone_code === zone.zone_code)
  if (idx !== -1) {
    zones.value[idx] = { ...zones.value[idx], status: nextStatus }
  }

  if (maintenanceId.value) {
    api.put(`/meals/${maintenanceId.value}/${zone.zone_code}`, { status: nextStatus })
      .catch(err => {
        console.error('Update failed:', err)
        // 回滾到先前狀態
        const rollbackIdx = zones.value.findIndex(z => z.zone_code === zone.zone_code)
        if (rollbackIdx !== -1) {
          zones.value[rollbackIdx] = { ...zones.value[rollbackIdx], status: prevStatus }
        }
      })
  }
}

const fetchZones = async () => {
  if (!maintenanceId.value) return
  try {
    const res = await api.get(`/meals/${maintenanceId.value}`)
    if (res.data?.zones) {
      res.data.zones.forEach(z => {
        const idx = zones.value.findIndex(x => x.zone_code === z.zone_code)
        if (idx !== -1) {
          zones.value[idx].status = normalizeStatus(z.status)
        }
      })
    }
  } catch (err) {
    console.error('Fetch failed:', err)
  }
}

// 開始輪詢
const startPolling = () => {
  stopPolling()
  pollTimer = setInterval(fetchZones, POLL_INTERVAL)
}

// 停止輪詢
const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch(maintenanceId, (id) => {
  if (id) {
    fetchZones()
    startPolling()
  } else {
    stopPolling()
  }
})

onMounted(() => {
  if (maintenanceId.value) {
    fetchZones()
    startPolling()
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.meal-sidebar {
  position: fixed;
  right: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  z-index: 40;
}

.meal-container {
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid #334155;
  border-radius: 0.5rem;
  padding: 0.375rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.zone-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.125rem;
}

.light {
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.light:hover {
  transform: scale(1.15);
}

.light-gray {
  background: #475569;
}

.light-red {
  background: #ff1744;
  box-shadow: 0 0 8px 1px rgba(255, 23, 68, 0.7), 0 0 14px 3px rgba(255, 23, 68, 0.3);
}

.light-green {
  background: #00e676;
  box-shadow: 0 0 8px 1px rgba(0, 230, 118, 0.7), 0 0 14px 3px rgba(0, 230, 118, 0.3);
}

.light-readonly {
  cursor: default;
}

.light-readonly:hover {
  transform: none;
}

.title {
  font-size: 0.65rem;
  font-weight: 600;
  color: #e2e8f0;
  text-align: center;
}

.bento-icon {
  font-size: 1rem;
  text-align: center;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid #334155;
  margin-bottom: 0.25rem;
  animation: bounce 2s ease-in-out infinite;
}

@keyframes bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}

.arrived-icon {
  font-size: 0.625rem;
  color: white;
  font-weight: bold;
  animation: check-pop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes check-pop {
  from { transform: scale(0); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

.zone-label {
  font-size: 0.625rem;
  color: #64748b;
}
</style>
