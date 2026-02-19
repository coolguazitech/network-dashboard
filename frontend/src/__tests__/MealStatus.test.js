import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import MealStatus from '../components/MealStatus.vue'

// Mock the api module
vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { zones: [] } }),
    put: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

// Mock auth module
vi.mock('@/utils/auth', () => ({
  canWrite: ref(true),
}))

describe('MealStatus', () => {
  const createWrapper = (maintenanceId = 'TEST-001') => {
    return mount(MealStatus, {
      global: {
        provide: {
          maintenanceId: ref(maintenanceId),
        },
      },
    })
  }

  it('renders three zones', () => {
    const wrapper = createWrapper()
    const zones = wrapper.findAll('.zone-item')
    expect(zones.length).toBe(3)
  })

  it('renders zone labels', () => {
    const wrapper = createWrapper()
    const labels = wrapper.findAll('.zone-label')
    const texts = labels.map(l => l.text())
    expect(texts).toContain('竹')
    expect(texts).toContain('中')
    expect(texts).toContain('南')
  })

  it('renders bento icon', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.bento-icon').text()).toContain('🍱')
  })

  it('renders title', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.title').text()).toBe('便當')
  })

  it('starts with all lights gray', () => {
    const wrapper = createWrapper()
    const lights = wrapper.findAll('.light-gray')
    expect(lights.length).toBe(3)
  })
})
