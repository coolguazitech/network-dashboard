import { describe, it, expect } from 'vitest'
import { classifyError, formatErrorMessage, ErrorType } from '../utils/api'

describe('ErrorType', () => {
  it('all types defined', () => {
    expect(ErrorType.NETWORK).toBe('network')
    expect(ErrorType.TIMEOUT).toBe('timeout')
    expect(ErrorType.NOT_FOUND).toBe('not_found')
    expect(ErrorType.VALIDATION).toBe('validation')
    expect(ErrorType.AUTH).toBe('auth')
    expect(ErrorType.SERVER).toBe('server')
    expect(ErrorType.UNKNOWN).toBe('unknown')
  })
})

describe('classifyError', () => {
  it('timeout error returns TIMEOUT type', () => {
    const error = { code: 'ECONNABORTED' }
    const result = classifyError(error)
    expect(result.type).toBe(ErrorType.TIMEOUT)
    expect(result.status).toBeNull()
  })

  it('network error returns NETWORK type', () => {
    const error = { message: 'Network Error' }
    const result = classifyError(error)
    expect(result.type).toBe(ErrorType.NETWORK)
    expect(result.status).toBeNull()
  })

  it('404 status returns NOT_FOUND type', () => {
    const result = classifyError(null, 404)
    expect(result.type).toBe(ErrorType.NOT_FOUND)
    expect(result.status).toBe(404)
  })

  it('401 status returns AUTH type', () => {
    const result = classifyError(null, 401)
    expect(result.type).toBe(ErrorType.AUTH)
    expect(result.status).toBe(401)
  })

  it('500 status returns SERVER type', () => {
    const result = classifyError(null, 500)
    expect(result.type).toBe(ErrorType.SERVER)
    expect(result.status).toBe(500)
  })

  it('unknown error returns UNKNOWN type', () => {
    const result = classifyError({})
    expect(result.type).toBe(ErrorType.UNKNOWN)
  })

  it('axios response error delegates to status-based classification', () => {
    const error = { response: { status: 403 } }
    const result = classifyError(error)
    expect(result.type).toBe(ErrorType.AUTH)
    expect(result.status).toBe(403)
  })
})

describe('formatErrorMessage', () => {
  it('with detail returns detail', () => {
    const error = { type: ErrorType.SERVER, message: 'Server error', detail: 'Database connection failed' }
    const result = formatErrorMessage(error)
    expect(result).toBe('Database connection failed')
  })

  it('without detail returns message', () => {
    const error = { type: ErrorType.NETWORK, message: 'Network error occurred' }
    const result = formatErrorMessage(error)
    expect(result).toBe('Network error occurred')
  })

  it('null returns default message', () => {
    const result = formatErrorMessage(null)
    expect(result).toBe('發生未知錯誤')
  })

  it('empty object returns default message', () => {
    const result = formatErrorMessage({})
    expect(result).toBe('發生未知錯誤')
  })
})
