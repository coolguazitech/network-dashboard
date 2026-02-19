import { describe, it, expect } from 'vitest'
import { useToast } from '../composables/useToast'

describe('useToast', () => {
  it('returns expected API', () => {
    const toast = useToast()
    expect(toast.messageModal).toBeDefined()
    expect(toast.confirmModal).toBeDefined()
    expect(typeof toast.showMessage).toBe('function')
    expect(typeof toast.closeMessage).toBe('function')
    expect(typeof toast.showConfirm).toBe('function')
    expect(typeof toast.handleConfirm).toBe('function')
    expect(typeof toast.cancelConfirm).toBe('function')
  })

  it('showMessage sets modal state', () => {
    const { messageModal, showMessage } = useToast()
    showMessage('Test message', 'success')
    expect(messageModal.show).toBe(true)
    expect(messageModal.message).toBe('Test message')
    expect(messageModal.type).toBe('success')
    expect(messageModal.title).toBe('成功')
  })

  it('showMessage error type sets title', () => {
    const { messageModal, showMessage } = useToast()
    showMessage('Error occurred', 'error')
    expect(messageModal.title).toBe('錯誤')
  })

  it('showMessage info type sets title', () => {
    const { messageModal, showMessage } = useToast()
    showMessage('Info message', 'info')
    expect(messageModal.title).toBe('提示')
  })

  it('showMessage with custom title', () => {
    const { messageModal, showMessage } = useToast()
    showMessage('Custom', 'info', 'Custom Title')
    expect(messageModal.title).toBe('Custom Title')
  })

  it('closeMessage hides modal', () => {
    const { messageModal, showMessage, closeMessage } = useToast()
    showMessage('Test')
    expect(messageModal.show).toBe(true)
    closeMessage()
    expect(messageModal.show).toBe(false)
  })

  it('showConfirm returns promise', () => {
    const { showConfirm } = useToast()
    const result = showConfirm('Are you sure?')
    expect(result).toBeInstanceOf(Promise)
  })

  it('handleConfirm resolves with true', async () => {
    const { showConfirm, handleConfirm } = useToast()
    const promise = showConfirm('Confirm?')
    handleConfirm()
    const result = await promise
    expect(result).toBe(true)
  })

  it('cancelConfirm resolves with false', async () => {
    const { showConfirm, cancelConfirm } = useToast()
    const promise = showConfirm('Cancel?')
    cancelConfirm()
    const result = await promise
    expect(result).toBe(false)
  })

  it('confirmModal state is set correctly', () => {
    const { confirmModal, showConfirm } = useToast()
    showConfirm('Test message', 'Test title')
    expect(confirmModal.show).toBe(true)
    expect(confirmModal.title).toBe('Test title')
    expect(confirmModal.message).toBe('Test message')
  })
})
