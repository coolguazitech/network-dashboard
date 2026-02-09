/**
 * 前端錯誤回報工具。
 *
 * 將 JS 錯誤透過 API 回報到後端 SystemLog。
 * 內建 debounce 防止短時間大量重複回報。
 */
import { getAuthHeaders } from './auth'

const REPORT_INTERVAL_MS = 5000 // 同一錯誤最少間隔 5 秒
const recentErrors = new Map() // key -> timestamp

/**
 * 回報錯誤到後端。
 */
async function reportError({ summary, detail, module }) {
  // Debounce: 同一 summary 5 秒內不重複回報
  const key = summary
  const now = Date.now()
  const lastReport = recentErrors.get(key)
  if (lastReport && now - lastReport < REPORT_INTERVAL_MS) {
    return
  }
  recentErrors.set(key, now)

  // 清理舊的 key（避免 Map 無限成長）
  if (recentErrors.size > 100) {
    for (const [k, t] of recentErrors) {
      if (now - t > 60000) recentErrors.delete(k)
    }
  }

  try {
    const headers = getAuthHeaders()
    // 未登入時不回報（沒有 token）
    if (!headers.Authorization) return

    await fetch('/api/v1/system-logs/frontend-error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify({
        summary: String(summary).slice(0, 500),
        detail: detail ? String(detail).slice(0, 5000) : null,
        module: module || null,
      }),
    })
  } catch {
    // 回報失敗時靜默處理，不能再拋錯
  }
}

/**
 * 安裝全域錯誤處理。
 *
 * @param {import('vue').App} app - Vue 應用實例
 */
export function setupErrorReporter(app) {
  // Vue 組件錯誤
  app.config.errorHandler = (err, instance, info) => {
    console.error('Vue error:', err)
    reportError({
      summary: `前端錯誤: ${err.message || err}`,
      detail: err.stack || String(err),
      module: instance?.$options?.name || info,
    })
  }

  // 未捕捉的 Promise rejection
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason
    reportError({
      summary: `未處理的 Promise 錯誤: ${reason?.message || reason}`,
      detail: reason?.stack || String(reason),
      module: 'global',
    })
  })
}

export { reportError }
