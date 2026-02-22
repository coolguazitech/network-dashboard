import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// Mock api module
vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { total: 3 } }),
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

import { useCaseBadge, refreshCaseBadge } from '../composables/useCaseBadge'

describe('useCaseBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns badgeCount ref', () => {
    const maintenanceIdRef = ref('TEST-001')
    const { badgeCount } = useCaseBadge(maintenanceIdRef)
    expect(badgeCount).toBeDefined()
    expect(typeof badgeCount.value).toBe('number')
  })

  it('refreshCaseBadge is a function', () => {
    expect(typeof refreshCaseBadge).toBe('function')
  })
})
