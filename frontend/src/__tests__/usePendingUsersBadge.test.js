import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// Mock api module
vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [{ is_active: false }, { is_active: true }] }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

// Mock auth module
vi.mock('@/utils/auth', () => ({
  canWrite: ref(true),
  isRoot: ref(true),
  currentUser: ref({ display_name: 'Root', role: 'ROOT' }),
  isAuthenticated: ref(true),
}))

import { usePendingUsersBadge } from '../composables/usePendingUsersBadge'

describe('usePendingUsersBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns pendingCount ref', () => {
    const { pendingCount } = usePendingUsersBadge()
    expect(pendingCount).toBeDefined()
    expect(typeof pendingCount.value).toBe('number')
  })

  it('refreshPending is a function', () => {
    const { refreshPending } = usePendingUsersBadge()
    expect(typeof refreshPending).toBe('function')
  })
})
