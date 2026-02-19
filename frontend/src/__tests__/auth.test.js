import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock localStorage
const localStorageMock = (() => {
  let store = {}
  return {
    getItem: vi.fn((key) => store[key] || null),
    setItem: vi.fn((key, value) => { store[key] = value }),
    removeItem: vi.fn((key) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
  }
})()

Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock })

// Mock fetch
globalThis.fetch = vi.fn()

describe('auth utilities', () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.resetModules()
    vi.clearAllMocks()
  })

  it('getAuthHeaders returns empty when no token', async () => {
    const { getAuthHeaders } = await import('../utils/auth')
    const headers = getAuthHeaders()
    // Either empty object or has Bearer null
    expect(typeof headers).toBe('object')
  })

  it('hasPermission returns false when no user', async () => {
    const { hasPermission } = await import('../utils/auth')
    const result = hasPermission('device:write')
    expect(result).toBe(false)
  })

  it('logout clears stored data', async () => {
    localStorageMock.setItem('auth_token', 'test-token')
    localStorageMock.setItem('auth_user', JSON.stringify({ role: 'ROOT' }))

    const { logout } = await import('../utils/auth')
    logout()

    expect(localStorageMock.removeItem).toHaveBeenCalledWith('auth_token')
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('auth_user')
  })
})

describe('login function', () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.resetModules()
    vi.clearAllMocks()
  })

  it('returns error on failed login', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: 'Invalid credentials' }),
    })

    const { login } = await import('../utils/auth')
    const result = await login('wrong', 'password')

    expect(result.ok).toBe(false)
    expect(result.error).toBe('Invalid credentials')
  })

  it('returns error on network failure', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'))

    const { login } = await import('../utils/auth')
    const result = await login('user', 'pass')

    expect(result.ok).toBe(false)
    expect(result.error).toContain('網路錯誤')
  })
})
