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

vi.mock('@/utils/auth', () => ({
  canWrite: ref(true),
  isRoot: ref(true),
  currentUser: ref({ display_name: 'Root', role: 'ROOT' }),
  isAuthenticated: ref(true),
  hasPermission: vi.fn(() => true),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showMessage: vi.fn(),
    closeMessage: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(true),
    handleConfirm: vi.fn(),
    cancelConfirm: vi.fn(),
    messageModal: ref({ visible: false }),
    confirmModal: ref({ visible: false }),
  }),
}))

vi.mock('@/composables/usePendingUsersBadge', () => ({
  usePendingUsersBadge: () => ({
    pendingCount: ref(0),
    refreshPending: vi.fn(),
  }),
}))

vi.mock('dayjs', () => {
  const dayjs = (val) => ({
    local: () => ({
      format: () => '2026-01-01 12:00',
    }),
  })
  dayjs.extend = vi.fn()
  dayjs.utc = (val) => ({
    local: () => ({
      format: () => '2026-01-01 12:00',
    }),
  })
  return { default: dayjs }
})

vi.mock('dayjs/plugin/utc', () => ({ default: {} }))

import Users from '../views/Users.vue'
import api from '@/utils/api'

describe('Users', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockImplementation((url) => {
      if (url === '/users') return Promise.resolve({ data: [] })
      if (url === '/users/roles/available') return Promise.resolve({ data: [
        { value: 'root', label: 'ROOT', description: 'Admin' },
        { value: 'pm', label: 'PM', description: 'Project Manager' },
        { value: 'guest', label: 'GUEST', description: 'Guest' },
      ] })
      if (url === '/maintenance') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: {} })
    })
  })

  const createWrapper = () => mount(Users, {
    global: {
      stubs: {
        Transition: false,
      },
    },
  })

  it('renders page title', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('使用者管理')
  })

  it('renders create user button', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    const addButton = wrapper.findAll('button').find(b => b.text().includes('新增使用者'))
    expect(addButton).toBeTruthy()
    expect(addButton.text()).toContain('新增使用者')
  })

  it('renders users table headers', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    const html = wrapper.html()
    expect(html).toContain('帳號')
    expect(html).toContain('顯示名稱')
    expect(html).toContain('Email')
    expect(html).toContain('角色')
  })

  it('shows pending users section when inactive users exist', async () => {
    api.get.mockImplementation((url) => {
      if (url === '/users') return Promise.resolve({ data: [
        { id: 1, username: 'active1', display_name: 'Active', role: 'pm', is_active: true, maintenance_id: 'M1' },
        { id: 2, username: 'pending1', display_name: 'Pending', role: 'guest', is_active: false, maintenance_id: 'M2' },
      ] })
      if (url === '/users/roles/available') return Promise.resolve({ data: [
        { value: 'root', label: 'ROOT', description: 'Admin' },
        { value: 'pm', label: 'PM', description: 'PM' },
        { value: 'guest', label: 'GUEST', description: 'Guest' },
      ] })
      if (url === '/maintenance') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: {} })
    })

    const wrapper = createWrapper()
    await flushPromises()

    const html = wrapper.html()
    expect(html).toContain('待啟用')
    expect(html).toContain('pending1')
  })

  it('shows empty state when no users', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    expect(wrapper.html()).toContain('尚無使用者資料')
  })

  it('displays active users in the list', async () => {
    api.get.mockImplementation((url) => {
      if (url === '/users') return Promise.resolve({ data: [
        { id: 1, username: 'admin', display_name: 'Admin User', role: 'root', email: 'admin@test.com', is_active: true, maintenance_id: null },
      ] })
      if (url === '/users/roles/available') return Promise.resolve({ data: [] })
      if (url === '/maintenance') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: {} })
    })

    const wrapper = createWrapper()
    await flushPromises()

    const html = wrapper.html()
    expect(html).toContain('admin')
    expect(html).toContain('Admin User')
  })
})
