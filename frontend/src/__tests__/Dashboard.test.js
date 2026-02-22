import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, nextTick } from 'vue'

// Mock api module
vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
  },
  downloadFile: vi.fn(),
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
    showConfirm: vi.fn(),
    handleConfirm: vi.fn(),
    cancelConfirm: vi.fn(),
    messageModal: { visible: false },
    confirmModal: { visible: false },
  }),
}))

// Mock useAnimatedNumber composable
vi.mock('@/composables/useAnimatedNumber', () => ({
  useAnimatedNumber: (source) => ({
    displayed: source,
  }),
}))

import Dashboard from '../views/Dashboard.vue'
import api from '@/utils/api'

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default mock for polling config
    api.get.mockImplementation((url) => {
      if (url === '/dashboard/config/frontend') {
        return Promise.resolve({ data: { polling_interval_seconds: 30 } })
      }
      if (url.includes('/summary')) {
        return Promise.resolve({
          data: {
            maintenance_id: 'MAINT-001',
            indicators: {},
            overall: {
              total_count: 0,
              pass_count: 0,
              fail_count: 0,
              pass_rate: 0.0,
              status: 'no-data',
            },
          },
        })
      }
      if (url.includes('/details')) {
        return Promise.resolve({
          data: { failures: [] },
        })
      }
      return Promise.resolve({ data: {} })
    })
  })

  const createWrapper = (maintenanceId = 'MAINT-001') => {
    return mount(Dashboard, {
      global: {
        provide: {
          maintenanceId: ref(maintenanceId),
        },
        stubs: {
          'v-chart': true,
          Transition: false,
        },
      },
    })
  }

  it('renders page title', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const title = wrapper.find('h1')
    expect(title.exists()).toBe(true)
    expect(title.text()).toContain('指標總覽')
  })

  it('shows loading state while fetching summary', async () => {
    // Polling config resolves immediately, but summary hangs
    api.get.mockImplementation((url) => {
      if (url === '/dashboard/config/frontend') {
        return Promise.resolve({ data: { polling_interval_seconds: 30 } })
      }
      // All other requests hang (including summary)
      return new Promise(() => {})
    })

    const wrapper = createWrapper()
    // Flush the polling config promise so fetchSummary starts and sets loading=true
    await flushPromises()
    await nextTick()

    // The loading overlay should be present
    const loadingText = wrapper.text()
    expect(loadingText).toContain('載入中')
  })

  it('renders indicator cards after data loads', async () => {
    api.get.mockImplementation((url) => {
      if (url === '/dashboard/config/frontend') {
        return Promise.resolve({ data: { polling_interval_seconds: 30 } })
      }
      if (url.includes('/summary')) {
        return Promise.resolve({
          data: {
            maintenance_id: 'MAINT-001',
            indicators: {
              transceiver: { total_count: 100, pass_count: 95, fail_count: 5, pass_rate: 95.0, collection_errors: 0, status: 'warning' },
              version: { total_count: 50, pass_count: 50, fail_count: 0, pass_rate: 100.0, collection_errors: 0, status: 'success' },
              fan: { total_count: 30, pass_count: 30, fail_count: 0, pass_rate: 100.0, collection_errors: 0, status: 'success' },
              power: { total_count: 30, pass_count: 28, fail_count: 2, pass_rate: 93.3, collection_errors: 0, status: 'warning' },
            },
            overall: {
              total_count: 210,
              pass_count: 203,
              fail_count: 7,
              pass_rate: 96.7,
              status: 'warning',
            },
          },
        })
      }
      if (url.includes('/details')) {
        return Promise.resolve({
          data: { failures: [{ device: 'SW-01', interface: 'Gi1/0/1', reason: 'TX Power low' }] },
        })
      }
      return Promise.resolve({ data: {} })
    })

    const wrapper = createWrapper()
    await flushPromises()

    // Should render indicator cards in the grid
    const cardGrid = wrapper.find('.grid.grid-cols-4')
    expect(cardGrid.exists()).toBe(true)

    // Check that indicator titles are rendered
    const text = wrapper.text()
    expect(text).toContain('TRANSCEIVER')
    expect(text).toContain('VERSION')
    expect(text).toContain('FAN')
    expect(text).toContain('POWER')

    // Check pass/total counts are displayed
    expect(text).toContain('95 / 100 通過')
    expect(text).toContain('50 / 50 通過')
  })

  it('calls dashboard summary API on mount', async () => {
    createWrapper()
    await flushPromises()

    // Should have called the polling config endpoint
    expect(api.get).toHaveBeenCalledWith('/dashboard/config/frontend')

    // Should have called the summary endpoint
    expect(api.get).toHaveBeenCalledWith('/dashboard/maintenance/MAINT-001/summary')
  })

  it('shows no-data prompt when no maintenance selected', async () => {
    const wrapper = mount(Dashboard, {
      global: {
        provide: {
          maintenanceId: ref(''),
        },
        stubs: {
          'v-chart': true,
          Transition: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('請先在頂部選擇歲修 ID')
  })

  it('renders overall pass rate', async () => {
    api.get.mockImplementation((url) => {
      if (url === '/dashboard/config/frontend') {
        return Promise.resolve({ data: { polling_interval_seconds: 30 } })
      }
      if (url.includes('/summary')) {
        return Promise.resolve({
          data: {
            maintenance_id: 'MAINT-001',
            indicators: {
              transceiver: { total_count: 10, pass_count: 10, fail_count: 0, pass_rate: 100.0, collection_errors: 0, status: 'success' },
            },
            overall: {
              total_count: 10,
              pass_count: 10,
              fail_count: 0,
              pass_rate: 100.0,
              status: 'success',
            },
          },
        })
      }
      if (url.includes('/details')) {
        return Promise.resolve({ data: { failures: [] } })
      }
      return Promise.resolve({ data: {} })
    })

    const wrapper = createWrapper()
    await flushPromises()

    // Overall pass rate should be displayed
    const text = wrapper.text()
    expect(text).toContain('整體通過率')
  })

  it('renders progress bar section', async () => {
    api.get.mockImplementation((url) => {
      if (url === '/dashboard/config/frontend') {
        return Promise.resolve({ data: { polling_interval_seconds: 30 } })
      }
      if (url.includes('/summary')) {
        return Promise.resolve({
          data: {
            maintenance_id: 'MAINT-001',
            indicators: {
              transceiver: { total_count: 10, pass_count: 8, fail_count: 2, pass_rate: 80.0, collection_errors: 0, status: 'warning' },
            },
            overall: {
              total_count: 10,
              pass_count: 8,
              fail_count: 2,
              pass_rate: 80.0,
              status: 'warning',
            },
          },
        })
      }
      if (url.includes('/details')) {
        return Promise.resolve({ data: { failures: [] } })
      }
      return Promise.resolve({ data: {} })
    })

    const wrapper = createWrapper()
    await flushPromises()

    // The progress bar section should show "驗收進度"
    expect(wrapper.text()).toContain('驗收進度')
    expect(wrapper.text()).toContain('項目通過')
  })
})
