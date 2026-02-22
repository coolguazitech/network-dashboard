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

// Mock useToast composable
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

import Switches from '../views/Switches.vue'
import api from '@/utils/api'

const mockSwitches = [
  {
    id: 1,
    hostname: 'core-switch-01',
    ip_address: '192.168.1.1',
    vendor: 'cisco',
    platform: 'ios',
    site: 'datacenter',
    model: 'C9300',
    is_active: true,
  },
  {
    id: 2,
    hostname: 'access-switch-02',
    ip_address: '192.168.1.2',
    vendor: 'aruba',
    platform: 'aruba_cx',
    site: 'office',
    model: 'CX6300',
    is_active: false,
  },
]

describe('Switches', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockResolvedValue({ data: { data: mockSwitches } })
  })

  const createWrapper = () => {
    return mount(Switches, {
      global: {
        stubs: {
          teleport: true,
          Transition: false,
        },
      },
    })
  }

  it('renders page title "設備管理"', () => {
    const wrapper = createWrapper()
    const title = wrapper.find('h1')
    expect(title.text()).toBe('設備管理')
  })

  it('renders switch table', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    const table = wrapper.find('table')
    expect(table.exists()).toBe(true)
  })

  it('shows add button for write users', () => {
    const wrapper = createWrapper()
    const buttons = wrapper.findAll('button')
    const addBtn = buttons.find(b => b.text().includes('新增設備'))
    expect(addBtn).toBeDefined()
  })

  it('renders hostname/IP columns', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    const headers = wrapper.findAll('th')
    const headerTexts = headers.map(h => h.text())
    expect(headerTexts).toContain('主機名稱')
    expect(headerTexts).toContain('IP 位址')
  })
})
