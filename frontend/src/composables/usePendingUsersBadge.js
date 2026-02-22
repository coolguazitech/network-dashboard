/**
 * 待啟用帳號徽章 composable
 * 定期查詢未啟用的使用者數量，用於全域導航的紅色徽章（僅 ROOT 可見）。
 */
import { ref, watch, onUnmounted } from 'vue'
import api from '@/utils/api'
import { isAuthenticated, isRoot } from '@/utils/auth'

const pendingCount = ref(0)
let _timer = null
let _subscriberCount = 0
let _fetching = false

async function fetchPendingCount() {
  if (!isAuthenticated.value || !isRoot.value) {
    pendingCount.value = 0
    return
  }
  if (_fetching) return

  _fetching = true
  try {
    const { data } = await api.get('/users', { params: { include_inactive: true } })
    pendingCount.value = (data || []).filter(u => !u.is_active).length
  } catch {
    // 靜默失敗
  } finally {
    _fetching = false
  }
}

function startPolling() {
  stopPolling()
  fetchPendingCount()
  _timer = setInterval(fetchPendingCount, 15000) // 每 15 秒檢查一次
}

function stopPolling() {
  if (_timer) {
    clearInterval(_timer)
    _timer = null
  }
}

export function usePendingUsersBadge() {
  _subscriberCount++

  // 監聽登入狀態變化，即時啟動/停止 polling
  watch(
    [isAuthenticated, isRoot],
    ([authed, root]) => {
      if (authed && root) {
        startPolling()
      } else {
        stopPolling()
        pendingCount.value = 0
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    _subscriberCount--
    // 只有所有訂閱者都卸載後才停止 polling
    if (_subscriberCount <= 0) {
      stopPolling()
      _subscriberCount = 0
    }
  })

  return { pendingCount, refreshPending: fetchPendingCount }
}
