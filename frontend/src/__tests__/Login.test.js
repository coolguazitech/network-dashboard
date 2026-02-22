import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

// Mock vue-router (Login.vue uses useRouter)
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    currentRoute: ref({ query: {} }),
  }),
}))

// Mock api module
vi.mock('@/utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

// Mock auth module — define inline, no external variable
vi.mock('@/utils/auth', () => ({
  login: vi.fn(),
}))

import Login from '../views/Login.vue'
import api from '@/utils/api'
import { login as mockLogin } from '@/utils/auth'

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default: loadMaintenances returns a list
    api.get.mockResolvedValue({
      data: [
        { id: 'MAINT-001', name: '2026 Spring Maintenance' },
        { id: 'MAINT-002', name: '2026 Fall Maintenance' },
      ],
    })
  })

  const createWrapper = () => {
    return mount(Login, {
      global: {
        stubs: {
          Transition: false,
        },
      },
    })
  }

  it('renders login form with username and password inputs', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const inputs = wrapper.findAll('input')
    // Login tab has username + password inputs
    expect(inputs.length).toBeGreaterThanOrEqual(2)

    const usernameInput = inputs.find(i => i.attributes('placeholder') === '請輸入帳號')
    const passwordInput = inputs.find(i => i.attributes('placeholder') === '請輸入密碼')
    expect(usernameInput).toBeTruthy()
    expect(passwordInput).toBeTruthy()
  })

  it('renders login and register tabs', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const tabTexts = buttons.map(b => b.text())
    expect(tabTexts).toContain('登入')
    expect(tabTexts).toContain('訪客註冊')
  })

  it('shows password toggle button', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    // The password toggle button is a button with tabindex="-1"
    const toggleBtn = wrapper.find('button[tabindex="-1"]')
    expect(toggleBtn.exists()).toBe(true)

    // Initially password is hidden (type="password")
    const passwordInput = wrapper.find('input[placeholder="請輸入密碼"]')
    expect(passwordInput.attributes('type')).toBe('password')

    // Click toggle to show password
    await toggleBtn.trigger('click')
    expect(passwordInput.attributes('type')).toBe('text')
  })

  it('login button is present', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const submitBtn = wrapper.find('button[type="submit"]')
    expect(submitBtn.exists()).toBe(true)
    expect(submitBtn.text()).toContain('登入')
  })

  it('switching to register tab shows registration form', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    // Click the register tab
    const buttons = wrapper.findAll('button')
    const registerTab = buttons.find(b => b.text() === '訪客註冊')
    expect(registerTab).toBeTruthy()
    await registerTab.trigger('click')

    // Registration form should now be visible with its fields
    const regUsernameInput = wrapper.find('input[placeholder="請設定帳號"]')
    expect(regUsernameInput.exists()).toBe(true)

    const regDisplayNameInput = wrapper.find('input[placeholder="您的名稱（不可與他人重複）"]')
    expect(regDisplayNameInput.exists()).toBe(true)

    const regPasswordInput = wrapper.find('input[placeholder="請設定密碼"]')
    expect(regPasswordInput.exists()).toBe(true)

    const regConfirmInput = wrapper.find('input[placeholder="再次輸入密碼"]')
    expect(regConfirmInput.exists()).toBe(true)

    // Submit button should say "申請帳號"
    const submitBtn = wrapper.find('button[type="submit"]')
    expect(submitBtn.text()).toContain('申請帳號')
  })

  it('registration form has maintenance_id selector', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    // Switch to register tab
    const buttons = wrapper.findAll('button')
    const registerTab = buttons.find(b => b.text() === '訪客註冊')
    await registerTab.trigger('click')

    // Should have a select element for maintenance selection
    const select = wrapper.find('select')
    expect(select.exists()).toBe(true)

    // The select should contain the maintenance options loaded from API
    const options = select.findAll('option')
    // First option is the placeholder, plus 2 maintenance options
    expect(options.length).toBe(3)
    expect(options[1].text()).toContain('2026 Spring Maintenance')
    expect(options[2].text()).toContain('2026 Fall Maintenance')
  })

  it('calls loadMaintenances on mount via api.get', async () => {
    createWrapper()
    await flushPromises()

    expect(api.get).toHaveBeenCalledWith('/auth/maintenances-public')
  })

  it('calls login from auth.js when form is submitted', async () => {
    mockLogin.mockResolvedValue({ ok: true })

    const wrapper = createWrapper()
    await flushPromises()

    // Fill in the login form
    const usernameInput = wrapper.find('input[placeholder="請輸入帳號"]')
    const passwordInput = wrapper.find('input[placeholder="請輸入密碼"]')
    await usernameInput.setValue('testuser')
    await passwordInput.setValue('testpass')

    // Submit the form
    const form = wrapper.find('form')
    await form.trigger('submit.prevent')
    await flushPromises()

    expect(mockLogin).toHaveBeenCalledWith('testuser', 'testpass')
  })
})
