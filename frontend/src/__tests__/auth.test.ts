import { describe, it, expect, beforeEach, vi } from 'vitest'
import axios from 'axios'
import { authState, login, logout } from '../auth'

describe('Auth store and lifecycle', () => {
  beforeEach(() => {
    localStorage.clear()
    authState.ready = true
    authState.token = ''
    authState.user = null
    authState.hasUsers = true
    authState.error = ''
    delete axios.defaults.headers.common.Authorization
  })

  it('stores and attaches token on successful login', async () => {
    vi.spyOn(axios, 'post').mockResolvedValueOnce({
      data: {
        access_token: 'test-jwt-token',
        token_type: 'bearer',
        user: { id: 1, username: 'admin', is_admin: true, created_at: '2026-01-01' },
      },
    })

    await login('admin', 'password123')
    expect(authState.token).toBe('test-jwt-token')
    expect(authState.user?.username).toBe('admin')
    expect(localStorage.getItem('he_manager_token')).toBe('test-jwt-token')
    expect(axios.defaults.headers.common.Authorization).toBe('Bearer test-jwt-token')
  })

  it('clears token and user on logout', async () => {
    authState.token = 'existing-token'
    localStorage.setItem('he_manager_token', 'existing-token')
    axios.defaults.headers.common.Authorization = 'Bearer existing-token'

    await logout()

    expect(authState.token).toBe('')
    expect(authState.user).toBeNull()
    expect(localStorage.getItem('he_manager_token')).toBeNull()
    expect(axios.defaults.headers.common.Authorization).toBeUndefined()
  })
})
