/**
 * 認證狀態管理
 */
import { ref, computed } from 'vue'

const TOKEN_KEY = 'auth_token'
const USER_KEY = 'auth_user'

// 認證狀態
const token = ref(localStorage.getItem(TOKEN_KEY) || null)
const user = ref(JSON.parse(localStorage.getItem(USER_KEY) || 'null'))

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
export const isRoot = computed(() => user.value?.role === 'root')

/**
 * 當前使用者角色
 */
export const userRole = computed(() => user.value?.role || null)

/**
 * 是否有寫入權限（root 和 pm 有，guest 沒有）
 */
export const canWrite = computed(() => {
  const role = user.value?.role
  return role === 'root' || role === 'pm'
})

/**
 * 檢查是否有指定權限（向後相容，現在基於角色）
 * @param {string} permission - 權限名稱
 * @returns {boolean}
 */
export function hasPermission(permission) {
  if (!user.value) return false
  // root 擁有所有權限
  if (user.value.role === 'root') return true
  // pm 有寫入權限
  if (user.value.role === 'pm') return true
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

  // 若 401 則自動登出
  if (res.status === 401) {
    logout()
    // 避免在登入頁面無限重定向
    if (!window.location.pathname.includes('/login')) {
      window.location.href = '/login'
    }
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
