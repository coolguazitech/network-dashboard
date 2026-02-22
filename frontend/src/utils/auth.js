/**
 * 認證狀態管理
 */
import { ref, computed } from 'vue'

const TOKEN_KEY = 'auth_token'
const USER_KEY = 'auth_user'

// 認證狀態
const token = ref(localStorage.getItem(TOKEN_KEY) || null)
let _parsedUser = null
try {
  _parsedUser = JSON.parse(localStorage.getItem(USER_KEY) || 'null')
} catch (e) {
  _parsedUser = null
  localStorage.removeItem(USER_KEY)
}
const user = ref(_parsedUser)

/**
 * 是否已登入
 */
export const isAuthenticated = computed(() => !!token.value)

/**
 * 當前使用者
 */
export const currentUser = computed(() => user.value)

/**
 * 是否為 root 使用者
 */
export const isRoot = computed(() => user.value?.role?.toUpperCase() === 'ROOT')

/**
 * 當前使用者角色
 */
export const userRole = computed(() => user.value?.role || null)

/**
 * 是否有寫入權限（root 和 pm 有，guest 沒有）
 */
export const canWrite = computed(() => {
  const role = user.value?.role?.toUpperCase()
  return role === 'ROOT' || role === 'PM'
})

/**
 * 檢查是否有指定權限（向後相容，現在基於角色）
 *
 * NOTE: The current RBAC model is role-based only. The `permission` parameter
 * is accepted for API compatibility but is not used in the check. Access is
 * determined solely by role: ROOT and PM receive full access; all other roles
 * (e.g. GUEST) are read-only and this function returns false. When granular
 * permission checking is needed in the future, implement it here.
 *
 * @param {string} permission - 權限名稱（currently unused — role-based only）
 * @returns {boolean}
 */
export function hasPermission(permission) {
  if (!user.value) return false
  const role = user.value.role?.toUpperCase()
  // root 擁有所有權限
  if (role === 'ROOT') return true
  // pm 有寫入權限
  if (role === 'PM') return true
  // guest 沒有權限
  return false
}

/**
 * 取得認證 headers
 * @returns {Object} 包含 Authorization header 的物件
 */
export function getAuthHeaders() {
  if (!token.value) return {}
  return {
    Authorization: `Bearer ${token.value}`,
  }
}

/**
 * 登入
 * @param {string} username
 * @param {string} password
 * @returns {Promise<{ok: boolean, error?: string}>}
 */
export async function login(username, password) {
  try {
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })

    if (!res.ok) {
      const err = await res.json()
      return { ok: false, error: err.detail || '登入失敗' }
    }

    const data = await res.json()

    // 儲存 token 和使用者資訊
    token.value = data.token
    user.value = data.user
    localStorage.setItem(TOKEN_KEY, data.token)
    localStorage.setItem(USER_KEY, JSON.stringify(data.user))

    return { ok: true }
  } catch (e) {
    console.error('登入錯誤:', e)
    return { ok: false, error: '網路錯誤，請稍後再試' }
  }
}

/**
 * 登出
 */
export function logout() {
  token.value = null
  user.value = null
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// 防止多個 401 同時觸發重複登出+跳轉
let _loggingOut = false

/**
 * 登出並跳轉至登入頁（帶去重保護）。
 * 多個併發 401 只會觸發一次跳轉。
 */
export function logoutAndRedirect() {
  if (_loggingOut) return
  _loggingOut = true
  logout()
  if (!window.location.pathname.includes('/login')) {
    window.location.href = '/login'
  }
  // 跳轉後重設旗標（若跳轉未發生，例如已在 /login）
  setTimeout(() => { _loggingOut = false }, 2000)
}

/**
 * 刷新使用者資訊
 * @returns {Promise<boolean>}
 */
export async function refreshUser() {
  if (!token.value) return false

  try {
    const res = await fetch('/api/v1/auth/me', {
      headers: getAuthHeaders(),
    })

    if (!res.ok) {
      // Token 無效，清除登入狀態
      if (res.status === 401) {
        logout()
      }
      return false
    }

    const data = await res.json()
    user.value = data
    localStorage.setItem(USER_KEY, JSON.stringify(data))
    return true
  } catch (e) {
    console.error('刷新使用者資訊錯誤:', e)
    return false
  }
}

/**
 * 變更密碼
 * @param {string} oldPassword
 * @param {string} newPassword
 * @returns {Promise<{ok: boolean, error?: string}>}
 */
export async function changePassword(oldPassword, newPassword) {
  try {
    const res = await fetch('/api/v1/auth/change-password', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify({
        old_password: oldPassword,
        new_password: newPassword,
      }),
    })

    if (!res.ok) {
      const err = await res.json()
      return { ok: false, error: err.detail || '變更失敗' }
    }

    return { ok: true }
  } catch (e) {
    console.error('變更密碼錯誤:', e)
    return { ok: false, error: '網路錯誤，請稍後再試' }
  }
}

/**
 * 帶認證的 fetch
 * @param {string} url
 * @param {Object} options
 * @returns {Promise<Response>}
 */
export async function authFetch(url, options = {}) {
  const headers = {
    ...options.headers,
    ...getAuthHeaders(),
  }

  const res = await fetch(url, { ...options, headers })

  // 若 401 則自動登出（透過 logoutAndRedirect 去重）
  if (res.status === 401) {
    logoutAndRedirect()
  }

  return res
}

/**
 * 初始化認證（檢查 token 是否有效）
 * @returns {Promise<boolean>}
 */
export async function initAuth() {
  if (!token.value) return false
  return await refreshUser()
}
