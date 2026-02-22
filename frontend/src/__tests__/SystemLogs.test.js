import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

// Mock the api module — define inline to avoid hoisting issues
vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
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

// Mock useAnimatedNumber composable
vi.mock('@/composables/useAnimatedNumber', () => ({
  useAnimatedNumber: (source) => ({ displayed: source }),
}))

// Mock dayjs
vi.mock('dayjs', () => {
  const dayjs = () => ({
    local: () => ({ format: () => '01-01 00:00:00' }),
  })
  dayjs.extend = vi.fn()
  dayjs.utc = () => ({
    local: () => ({ format: () => '01-01 00:00:00' }),
  })
  return { default: dayjs }
})

vi.mock('dayjs/plugin/utc', () => ({ default: {} }))

import SystemLogs from '../views/SystemLogs.vue'
import api from '@/utils/api'

describe('SystemLogs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockImplementation((url) => {
      if (url.includes('/system-logs/stats')) {
        return Promise.resolve({ data: { error: 5, warning: 10, info: 100, total: 115 } })
      }
      if (url.includes('/system-logs')) {
        return Promise.resolve({ data: { items: [], total: 0, page: 1, total_pages: 0 } })
      }
      if (url === '/maintenance') {
        return Promise.resolve({ data: [] })
      }
      return Promise.resolve({ data: {} })
    })
  })

  const createWrapper = () => {
    return mount(SystemLogs, {
      global: {
        stubs: {
          Transition: false,
        },
      },
    })
  }

  it('renders page title "系統日誌"', () => {
    const wrapper = createWrapper()
    const title = wrapper.find('h1')
    expect(title.text()).toBe('系統日誌')
  })

  it('renders stat cards for ERROR, WARNING, INFO', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('ERROR')
    expect(text).toContain('WARNING')
    expect(text).toContain('INFO')
  })

  it('renders filter buttons for log levels', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    // The stat cards also serve as filter buttons
    const buttons = wrapper.findAll('button')
    // Find buttons that contain level text
    const errorBtn = buttons.find(b => b.text().includes('ERROR'))
    const warningBtn = buttons.find(b => b.text().includes('WARNING'))
    const infoBtn = buttons.find(b => b.text().includes('INFO'))
    expect(errorBtn).toBeDefined()
    expect(warningBtn).toBeDefined()
    expect(infoBtn).toBeDefined()
  })

  it('renders search input', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    const searchInput = wrapper.find('input[type="text"][placeholder*="搜尋"]')
    expect(searchInput.exists()).toBe(true)
  })

  it('renders cleanup button', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    const buttons = wrapper.findAll('button')
    const cleanupBtn = buttons.find(b => b.text().includes('清理舊日誌'))
    expect(cleanupBtn).toBeDefined()
  })
})
