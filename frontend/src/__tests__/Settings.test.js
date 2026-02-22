import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import Settings from '../views/Settings.vue'

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

describe('Settings', () => {
  const createWrapper = () => mount(Settings, {
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
    expect(wrapper.find('h1').text()).toContain('設置')
  })

  it('renders 3 tab buttons (Uplink, Version, Port Channel)', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const tabButtons = wrapper.findAll('button').filter(b => {
      const text = b.text()
      return text.includes('Uplink 期望') || text.includes('Version 期望') || text.includes('Port Channel 期望')
    })
    expect(tabButtons.length).toBe(3)
    expect(tabButtons[0].text()).toContain('Uplink 期望')
    expect(tabButtons[1].text()).toContain('Version 期望')
    expect(tabButtons[2].text()).toContain('Port Channel 期望')
  })

  it('defaults to uplink tab', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    expect(wrapper.vm.activeTab).toBe('uplink')
    expect(wrapper.find('h3').text()).toContain('Uplink 期望')
  })

  it('switching tabs works', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    // Switch to version tab
    const versionTabBtn = wrapper.findAll('button').find(b => b.text().includes('Version 期望'))
    await versionTabBtn.trigger('click')
    await flushPromises()
    expect(wrapper.vm.activeTab).toBe('version')
    expect(wrapper.find('h3').text()).toContain('Version 期望')

    // Switch to port channel tab
    const pcTabBtn = wrapper.findAll('button').find(b => b.text().includes('Port Channel 期望'))
    await pcTabBtn.trigger('click')
    await flushPromises()
    expect(wrapper.vm.activeTab).toBe('portchannel')
    expect(wrapper.find('h3').text()).toContain('Port Channel 期望')
  })

  it('search input is present', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const searchInput = wrapper.find('input[type="text"][placeholder*="搜尋"]')
    expect(searchInput.exists()).toBe(true)
  })

  it('add button is present for write users', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const addButton = wrapper.findAll('button').find(b => b.text().includes('新增期望'))
    expect(addButton).toBeTruthy()
    expect(addButton.text()).toContain('新增期望')
  })

  it('CSV import and export buttons are present', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const html = wrapper.html()
    expect(html).toContain('匯入 CSV')
    expect(html).toContain('匯出 CSV')
    expect(html).toContain('下載範本')
  })
})
