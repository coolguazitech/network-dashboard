import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

// Mock api module
vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
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

// Mock useToast composable
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showMessage: vi.fn(),
    closeMessage: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false),
    handleConfirm: vi.fn(),
    cancelConfirm: vi.fn(),
    messageModal: { visible: false },
    confirmModal: { visible: false },
  }),
}))

// Mock useCaseBadge composable
vi.mock('@/composables/useCaseBadge', () => ({
  refreshCaseBadge: vi.fn(),
}))

import Cases from '../views/Cases.vue'
import api from '@/utils/api'

describe('Cases', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default mock implementations
    api.get.mockImplementation((url) => {
      if (url.includes('/stats')) {
        return Promise.resolve({
          data: {
            total: 15,
            active: 10,
            assigned: 3,
            in_progress: 4,
            discussing: 2,
            resolved: 5,
            ping_unreachable: 1,
          },
        })
      }
      if (url.includes('/display-names')) {
        return Promise.resolve({ data: ['Alice', 'Bob', 'Charlie'] })
      }
      if (url.match(/\/cases\/[^/]+$/)) {
        return Promise.resolve({
          data: {
            cases: [
              {
                id: 1,
                mac_address: 'AA:BB:CC:DD:EE:01',
                ip_address: '192.168.1.1',
                status: 'ASSIGNED',
                assignee: 'Alice',
                last_ping_reachable: true,
                description: 'Test case 1',
                summary: '',
                change_tags: [],
              },
              {
                id: 2,
                mac_address: 'AA:BB:CC:DD:EE:02',
                ip_address: '192.168.1.2',
                status: 'IN_PROGRESS',
                assignee: 'Bob',
                last_ping_reachable: false,
                description: 'Test case 2',
                summary: '',
                change_tags: [],
              },
            ],
            total_pages: 1,
            total: 2,
          },
        })
      }
      return Promise.resolve({ data: {} })
    })
  })

  const createWrapper = (maintenanceId = 'MAINT-001') => {
    return mount(Cases, {
      global: {
        provide: {
          maintenanceId: ref(maintenanceId),
        },
        stubs: {
          teleport: true,
          Transition: false,
          transition: false,
        },
      },
    })
  }

  it('renders page title', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const title = wrapper.find('h1')
    expect(title.exists()).toBe(true)
    expect(title.text()).toBe('案件管理')
  })

  it('shows prompt when no maintenance selected', async () => {
    const wrapper = createWrapper('')
    await flushPromises()

    expect(wrapper.text()).toContain('請先在頂部選擇歲修 ID')
  })

  it('renders stat cards when maintenance selected and data loaded', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const text = wrapper.text()
    // The statusBreakdown should render stat cards for: 新案件, 處理中, 待討論, and 已結案
    expect(text).toContain('新案件')
    expect(text).toContain('處理中')
    expect(text).toContain('待討論')
    expect(text).toContain('已結案')

    // Check stat values are present
    expect(text).toContain('3')  // assigned
    expect(text).toContain('4')  // in_progress
    expect(text).toContain('2')  // discussing
    expect(text).toContain('5')  // resolved
  })

  it('renders status filter buttons', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const text = wrapper.text()
    // statusFilterOptions labels
    expect(text).toContain('全部')
    expect(text).toContain('未結案')
    expect(text).toContain('新案件')
    expect(text).toContain('處理中')
    expect(text).toContain('待討論')
    expect(text).toContain('已結案')
  })

  it('renders ping filter buttons', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const text = wrapper.text()
    // pingFilterOptions labels
    expect(text).toContain('不限')
    expect(text).toContain('不可達')
    expect(text).toContain('可達')
  })

  it('shows sync button for write users', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const syncBtn = buttons.find(b => b.text().includes('同步案件'))
    expect(syncBtn).toBeTruthy()
  })

  it('calls loadStats and loadCases on mount with maintenanceId', async () => {
    createWrapper()
    await flushPromises()

    // Should have called stats endpoint
    expect(api.get).toHaveBeenCalledWith(
      expect.stringContaining('/cases/MAINT-001/stats')
    )

    // Should have called cases list endpoint
    expect(api.get).toHaveBeenCalledWith(
      expect.stringContaining('/cases/MAINT-001'),
      expect.objectContaining({
        params: expect.objectContaining({ page: 1, page_size: 50 }),
      })
    )

    // Should have called user display names
    expect(api.get).toHaveBeenCalledWith('/users/display-names')
  })

  it('renders case list items when data is loaded', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('AA:BB:CC:DD:EE:01')
    expect(text).toContain('AA:BB:CC:DD:EE:02')
    expect(text).toContain('192.168.1.1')
    expect(text).toContain('192.168.1.2')
  })

  it('shows active case count in header', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    expect(wrapper.text()).toContain('10 件進行中')
  })

  it('shows search input', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const searchInput = wrapper.find('input[placeholder="搜尋 MAC / IP..."]')
    expect(searchInput.exists()).toBe(true)
  })
})
