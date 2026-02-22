import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import Contacts from '../views/Contacts.vue'

// Mock the api module
vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
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

describe('Contacts', () => {
  const createWrapper = (maintenanceId = 'TEST-001') => {
    return mount(Contacts, {
      global: {
        provide: {
          maintenanceId: ref(maintenanceId),
        },
      },
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders page title "通訊錄"', () => {
    const wrapper = createWrapper()
    const title = wrapper.find('h1')
    expect(title.text()).toBe('通訊錄')
  })

  it('renders category sidebar', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    // The sidebar contains the category heading "分類"
    const sidebar = wrapper.find('.w-48')
    expect(sidebar.exists()).toBe(true)
    expect(wrapper.text()).toContain('分類')
  })

  it('renders contact list area', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    // The right-side contact list area (flex-1)
    const listArea = wrapper.find('.flex-1')
    expect(listArea.exists()).toBe(true)
  })

  it('shows add category button', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    // The "+" button to add a category is inside the sidebar header
    const addCategoryBtn = wrapper.find('button[title="新增分類"]')
    expect(addCategoryBtn.exists()).toBe(true)
    expect(addCategoryBtn.text()).toBe('+')
  })

  it('shows add contact button for write users', () => {
    const wrapper = createWrapper()
    // The "新增聯絡人" button should be visible for write users
    const buttons = wrapper.findAll('button')
    const addContactBtn = buttons.find(b => b.text().includes('新增聯絡人'))
    expect(addContactBtn).toBeDefined()
  })

  it('search input present', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    const searchInput = wrapper.find('input[type="text"][placeholder*="搜尋"]')
    expect(searchInput.exists()).toBe(true)
  })
})
