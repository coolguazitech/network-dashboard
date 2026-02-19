/**
 * API 工具函式
 * 統一處理 API 請求和錯誤分類
 */
import axios from 'axios'

// 建立 axios 實例
const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 請求攔截器 - 自動附加 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 回應攔截器 - 處理 401 錯誤
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token')
      localStorage.removeItem('auth_user')
      // 避免在登入頁面無限重定向
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// 導出 axios 實例作為 default
export default api

/**
 * 透過 axios（含 auth token）下載檔案並觸發瀏覽器存檔。
 * 取代 window.open() 以避免認證繞過。
 *
 * @param {string} path - API 路徑 (相對於 /api/v1)
 * @param {string} filename - 下載的檔名
 * @param {string} [mimeType='text/csv;charset=utf-8;'] - MIME type
 */
export async function downloadFile(path, filename, mimeType = 'text/csv;charset=utf-8;') {
  const response = await api.get(path, { responseType: 'blob' })
  const blob = new Blob([response.data], { type: mimeType })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  link.setAttribute('href', url)
  link.setAttribute('download', filename)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * API 錯誤類別
 */
export const ErrorType = {
  NETWORK: 'network',       // 網路錯誤（無法連線）
  TIMEOUT: 'timeout',       // 請求超時
  NOT_FOUND: 'not_found',   // 資源不存在
  VALIDATION: 'validation', // 驗證錯誤
  AUTH: 'auth',             // 認證/授權錯誤
  SERVER: 'server',         // 伺服器內部錯誤
  UNKNOWN: 'unknown',       // 未知錯誤
};

/**
 * 錯誤訊息對應
 */
const ERROR_MESSAGES = {
  [ErrorType.NETWORK]: '網路連線失敗，請檢查網路狀態',
  [ErrorType.TIMEOUT]: '請求超時，請稍後再試',
  [ErrorType.NOT_FOUND]: '找不到請求的資源',
  [ErrorType.VALIDATION]: '輸入資料有誤',
  [ErrorType.AUTH]: '認證失敗，請重新登入',
  [ErrorType.SERVER]: '伺服器發生錯誤，請稍後再試',
  [ErrorType.UNKNOWN]: '發生未知錯誤',
};

/**
 * 分類 API 錯誤
 * @param {Error|Response} error - 錯誤物件或 Response
 * @param {number|null} status - HTTP 狀態碼（若為 Error 則為 null）
 * @returns {Object} 錯誤資訊 { type, message, status }
 */
export function classifyError(error, status = null) {
  // 如果是 fetch 網路錯誤
  if (error instanceof TypeError && error.message.includes('fetch')) {
    return {
      type: ErrorType.NETWORK,
      message: ERROR_MESSAGES[ErrorType.NETWORK],
      status: null,
    };
  }

  // 如果是 AbortError（超時）
  if (error.name === 'AbortError') {
    return {
      type: ErrorType.TIMEOUT,
      message: ERROR_MESSAGES[ErrorType.TIMEOUT],
      status: null,
    };
  }

  // 根據 HTTP 狀態碼分類
  const httpStatus = status || error?.status;
  if (httpStatus) {
    if (httpStatus === 404) {
      return {
        type: ErrorType.NOT_FOUND,
        message: ERROR_MESSAGES[ErrorType.NOT_FOUND],
        status: httpStatus,
      };
    }
    if (httpStatus === 400 || httpStatus === 422) {
      return {
        type: ErrorType.VALIDATION,
        message: ERROR_MESSAGES[ErrorType.VALIDATION],
        status: httpStatus,
      };
    }
    if (httpStatus === 401 || httpStatus === 403) {
      return {
        type: ErrorType.AUTH,
        message: ERROR_MESSAGES[ErrorType.AUTH],
        status: httpStatus,
      };
    }
    if (httpStatus >= 500) {
      return {
        type: ErrorType.SERVER,
        message: ERROR_MESSAGES[ErrorType.SERVER],
        status: httpStatus,
      };
    }
  }

  return {
    type: ErrorType.UNKNOWN,
    message: ERROR_MESSAGES[ErrorType.UNKNOWN],
    status: httpStatus || null,
  };
}

/**
 * 解析 API 錯誤回應
 * @param {Response} response - fetch Response 物件
 * @returns {Promise<Object>} 解析後的錯誤資訊 { type, message, detail, status }
 */
export async function parseApiError(response) {
  const classified = classifyError(null, response.status);

  try {
    const data = await response.json();
    // 後端 FastAPI 通常返回 { detail: "..." }
    const detail = data.detail || data.message || data.error;

    return {
      ...classified,
      message: detail || classified.message,
      detail: typeof detail === 'object' ? JSON.stringify(detail) : detail,
    };
  } catch {
    // JSON 解析失敗
    return classified;
  }
}

/**
 * 封裝的 fetch 函式，自動處理錯誤
 * @param {string} url - 請求 URL
 * @param {Object} options - fetch 選項
 * @param {number} timeout - 超時時間（毫秒），預設 30000
 * @returns {Promise<Object>} { ok: boolean, data?: any, error?: Object }
 */
export async function apiFetch(url, options = {}, timeout = 30000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  // 自動加入認證 token
  const token = localStorage.getItem('auth_token');
  const headers = {
    ...options.headers,
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const error = await parseApiError(response);
      return { ok: false, error };
    }

    // 處理空回應
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      return { ok: true, data: null };
    }

    const data = await response.json();
    return { ok: true, data };
  } catch (error) {
    clearTimeout(timeoutId);
    const classified = classifyError(error);
    return { ok: false, error: classified };
  }
}

/**
 * 格式化錯誤訊息供 UI 顯示
 * @param {Object} error - classifyError 或 parseApiError 返回的錯誤物件
 * @returns {string} 格式化的錯誤訊息
 */
export function formatErrorMessage(error) {
  if (!error) return '發生未知錯誤';

  // 如果有具體的 detail，優先使用
  if (error.detail && error.detail !== error.message) {
    return error.detail;
  }

  return error.message || '發生未知錯誤';
}
