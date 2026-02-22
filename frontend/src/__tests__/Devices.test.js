import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import Devices from '../views/Devices.vue'

vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
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

describe('Devices', () => {
  const createWrapper = () => mount(Devices, {
    global: {
      provide: {
        maintenanceId: ref('MAINT-001'),
        refreshMaintenanceList: vi.fn(),
      },
    },
  })

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('renders page title', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('設備管理')
  })

  it('renders tab buttons "Client 清單" and "設備清單"', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    const buttons = wrapper.findAll('button').filter(b => {
      const text = b.text()
      return text.includes('Client 清單') || text.includes('設備清單')
    })
    expect(buttons.length).toBe(2)
    expect(buttons[0].text()).toContain('Client 清單')
    expect(buttons[1].text()).toContain('設備清單')
  })

  it('defaults to maclist tab', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    expect(wrapper.vm.activeTab).toBe('maclist')
    expect(wrapper.find('h3').text()).toContain('Client 清單')
  })

  it('switching tabs updates active state', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    // Find the device tab button and click it
    const deviceTabBtn = wrapper.findAll('button').find(b => b.text().includes('設備清單'))
    await deviceTabBtn.trigger('click')
    await flushPromises()

    expect(wrapper.vm.activeTab).toBe('devices')
    expect(wrapper.find('h3').text()).toContain('設備清單與對應')
  })

  it('client tab shows "新增 Client" button for write users', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const addButton = wrapper.findAll('button').find(b => b.text().includes('新增 Client'))
    expect(addButton).toBeTruthy()
    expect(addButton.text()).toContain('新增 Client')
  })

  it('device tab shows "新增設備" button', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    // Switch to devices tab
    const deviceTabBtn = wrapper.findAll('button').find(b => b.text().includes('設備清單'))
    await deviceTabBtn.trigger('click')
    await flushPromises()

    const addButton = wrapper.findAll('button').find(b => b.text().includes('新增設備'))
    expect(addButton).toBeTruthy()
    expect(addButton.text()).toContain('新增設備')
  })

  it('renders search input on maclist tab', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const searchInput = wrapper.find('input[type="text"][placeholder*="搜尋"]')
    expect(searchInput.exists()).toBe(true)
  })
})
