import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { authState, initAuth, login, logout, retryAuth } from '../auth'

const originalAdapter = axios.defaults.adapter
const user = (id: number) => ({ id, username: `reader-${id}`, is_admin: false, is_active: true, created_at: '' })
const response = (config: InternalAxiosRequestConfig, data: unknown) => ({ config, data, status: 200, statusText: 'OK', headers: {} })
const fail = (config: InternalAxiosRequestConfig, status: number): never => {
  throw new AxiosError('fixture failure', AxiosError.ERR_BAD_RESPONSE, config, undefined,
    { ...response(config, { detail: 'fixture failure' }), status })
}
const deferred = () => {
  let resolve!: () => void
  const promise = new Promise<void>(done => { resolve = done })
  return { promise, resolve }
}
const storedToken = (token: string) => {
  authState.token = token
  localStorage.setItem('he_manager_token', token)
}

beforeEach(() => {
  localStorage.clear()
  delete axios.defaults.headers.common.Authorization
  Object.assign(authState, { ready: false, token: '', user: null, error: '', hasUsers: true })
})
afterEach(() => { axios.defaults.adapter = originalAdapter })

describe('authentication through the real Axios interceptor chain', () => {
  it('finishes initialization after the interceptor clears an expired token', async () => {
    storedToken('expired')
    axios.defaults.adapter = async config => {
      if (config.url?.endsWith('/auth/status')) return response(config, { has_users: true })
      expect(config.headers.get('Authorization')).toBe('Bearer expired')
      return fail(config, 401)
    }
    await initAuth()
    expect(authState.ready).toBe(true)
    expect(authState.user).toBeNull()
    expect(authState.token).toBe('')
    expect(localStorage.getItem('he_manager_token')).toBeNull()
  })

  it('preserves credentials after a status timeout without admitting an unverified user', async () => {
    storedToken('valid')
    axios.defaults.adapter = async config => { throw new AxiosError('timeout', 'ECONNABORTED', config) }
    await initAuth()
    expect(authState.ready).toBe(true)
    expect(authState.token).toBe('valid')
    expect(authState.user).toBeNull()
    expect(authState.error).toContain('连接后端超时')
  })

  it('keeps a valid token on a temporary /me failure and restores the user on retry', async () => {
    storedToken('valid')
    let available = false
    axios.defaults.adapter = async config => {
      if (config.url?.endsWith('/auth/status')) return response(config, { has_users: true })
      return available ? response(config, user(1)) : fail(config, 503)
    }
    await initAuth()
    expect(authState.ready).toBe(true)
    expect(authState.token).toBe('valid')
    expect(authState.user).toBeNull()
    expect(authState.error).toBeTruthy()
    available = true
    await retryAuth()
    expect(authState.ready).toBe(true)
    expect(authState.user?.id).toBe(1)
    expect(authState.error).toBe('')
  })

  for (const status of [200, 401]) {
    it(`ignores a late old /me ${status} after a fresh login`, async () => {
      storedToken('old')
      const pending = deferred()
      let meStarted = false
      axios.defaults.adapter = async config => {
        if (config.url?.endsWith('/auth/status')) return response(config, { has_users: true })
        if (config.url?.endsWith('/auth/login')) return response(config, { access_token: 'new', user: user(2) })
        meStarted = true
        expect(config.headers.get('Authorization')).toBe('Bearer old')
        await pending.promise
        return status === 401 ? fail(config, 401) : response(config, user(1))
      }
      const initialization = initAuth()
      await flushPromises()
      expect(meStarted).toBe(true)
      await login('reader-2', 'fixture')
      pending.resolve()
      await initialization
      expect(authState.ready).toBe(true)
      expect(authState.token).toBe('new')
      expect(authState.user?.id).toBe(2)
    })
  }

  it('does not expire a fresh login when an old media request returns 401', async () => {
    storedToken('old')
    const pending = deferred()
    let mediaStarted = false
    axios.defaults.adapter = async config => {
      if (config.url?.endsWith('/auth/login')) return response(config, { access_token: 'new', user: user(2) })
      mediaStarted = true
      expect(config.headers.get('Authorization')).toBe('Bearer old')
      await pending.promise
      return fail(config, 401)
    }
    const oldRequest = axios.get('/media/1').catch(error => error)
    await flushPromises()
    expect(mediaStarted).toBe(true)
    await login('reader-2', 'fixture')
    pending.resolve()
    expect((await oldRequest).response.status).toBe(401)
    expect(authState.token).toBe('new')
    expect(authState.user?.id).toBe(2)
  })

  it('does not let a slow logout erase a newer explicit login', async () => {
    storedToken('old')
    const pending = deferred()
    axios.defaults.adapter = async config => {
      if (config.url?.endsWith('/auth/login')) return response(config, { access_token: 'new', user: user(2) })
      await pending.promise
      return response(config, {})
    }
    const signingOut = logout()
    await flushPromises()
    await login('reader-2', 'fixture')
    pending.resolve()
    await signingOut
    expect(authState.ready).toBe(true)
    expect(authState.token).toBe('new')
    expect(authState.user?.id).toBe(2)
  })
})
