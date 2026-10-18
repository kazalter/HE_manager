import { beforeEach, describe, expect, it, vi } from 'vitest'
import axios, { AxiosHeaders } from 'axios'
import type { DesktopSessionSnapshot } from '../desktop-contract'
const host = vi.hoisted(() => ({ authentication: vi.fn(), login: vi.fn(), logout: vi.fn(), restoreLogin: vi.fn(), onSessionChanged: vi.fn(), listener: undefined as ((value: DesktopSessionSnapshot) => void) | undefined }))
vi.mock('../desktop', async () => {
 const { reactive } = await import('vue')
 return { desktopBridge: host, desktopSession: reactive({ revision: -1, generation: '', user: null }) }
})
import { authIdentity, authState, initAuth, login, logout } from '../auth'
import { desktopSession } from '../desktop'
import { authUrl } from '../config'
const state = (generation = 'session-a', revision = 1, id: number | null = 1): DesktopSessionSnapshot => ({ server: 'https://he.example', generation, revision, hasUsers: true, persistent: true, restoring: false, error: '', user: id ? { id, username: 'account-' + id, is_admin: false, is_active: true, created_at: '' } : null })
beforeEach(async () => {
 vi.clearAllMocks(); localStorage.clear(); desktopSession.revision = -1; authState.user = null; authState.token = ''
 host.onSessionChanged.mockImplementation(callback => { host.listener = callback; return () => {} })
 host.authentication.mockResolvedValue(state())
 host.login.mockResolvedValue(state('session-b', 2, 2)); host.logout.mockResolvedValue(state('logged-out', 3, null))
 await initAuth()
})
describe('desktop renderer authentication', () => {
 it('uses only host login snapshots and never persists or sends a renderer credential', async () => {
  localStorage.setItem('he_manager_token', 'legacy-renderer-secret')
  await initAuth(); await login('account-2', 'private-password')
  expect(host.login).toHaveBeenCalledWith({ username: 'account-2', password: 'private-password' })
  expect(authState.token).toBe(''); expect(localStorage.getItem('he_manager_token')).toBeNull()
  expect(authIdentity()).toBe('session-b')
  const source = authUrl('/stream/7?token=legacy-renderer-secret')
  expect(source).toBe('he://app/stream/7?he_session=session-b')
  let observed: AxiosHeaders | undefined
  await axios.get('/media', { adapter: async config => { observed = config.headers; return { data: [], status: 200, statusText: 'OK', headers: {}, config } } })
  expect(observed!.get('X-HE-Generation')).toBe('session-b'); expect(observed!.get('Authorization')).toBeUndefined()
  await logout(); expect(authState.user).toBeNull(); expect(authIdentity()).toBe('')
 })
 it('discards an old successful response after the host changes identities', async () => {
  let complete!: () => void
  const pending = axios.get('/media', { adapter: config => new Promise(resolve => { complete = () => resolve({ data: [{ id: 1 }], status: 200, statusText: 'OK', headers: {}, config }) }) })
  const rejected = expect(pending).rejects.toMatchObject({ code: 'ERR_CANCELED' })
  await vi.waitFor(() => expect(complete).toBeTypeOf('function'))
  host.listener!(state('session-new', 10, 2)); complete(); await rejected
  expect(authState.user?.id).toBe(2)
 })
 it('ignores a late lower revision snapshot without reviving the previous identity', async () => {
  host.listener!(state('newer', 12, 2))
  host.login.mockResolvedValueOnce(state('older', 11, 1))
  await login('account-1', 'pw')
  expect(authIdentity()).toBe('newer'); expect(authState.user?.id).toBe(2)
 })
})
