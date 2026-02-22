/**
 * 案件徽章 composable
 * 定期查詢「指派給我但尚未接受」的案件數量，用於全域導航的紅色徽章。
 */
import { ref, watch, onUnmounted } from 'vue'
import api from '@/utils/api'
import { currentUser, isAuthenticated } from '@/utils/auth'

const badgeCount = ref(0)
let _timer = null
let _maintenanceId = null
let _fetching = false

async function fetchBadgeCount() {
  if (!_maintenanceId || !isAuthenticated.value) {
    badgeCount.value = 0
    return
  }
  if (_fetching) return
  const displayName = currentUser.value?.display_name
  if (!displayName) return

  _fetching = true
  try {
    const { data } = await api.get(`/cases/${encodeURIComponent(_maintenanceId)}`, {
      params: {
        status: 'ASSIGNED',
        assignee: displayName,
        page_size: 1,
      },
    })
    badgeCount.value = data.total || 0
  } catch {
    // 靜默失敗，不影響 UI
  } finally {
    _fetching = false
  }
}

function startPolling() {
  stopPolling()
  fetchBadgeCount()
  _timer = setInterval(fetchBadgeCount, 30000)
}

function stopPolling() {
  if (_timer) {
    clearInterval(_timer)
    _timer = null
  }
}

/**
 * @param {import('vue').Ref<string>} maintenanceIdRef - 當前歲修 ID
 */
/** 獨立匯出：允許任何元件直接觸發徽章刷新（不需再呼叫 useCaseBadge） */
export const refreshCaseBadge = fetchBadgeCount

export function useCaseBadge(maintenanceIdRef) {
  watch(
    maintenanceIdRef,
    (newId) => {
      _maintenanceId = newId
      if (newId) {
        startPolling()
      } else {
        stopPolling()
        badgeCount.value = 0
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    stopPolling()
  })

  return { badgeCount, refreshBadge: fetchBadgeCount }
}
