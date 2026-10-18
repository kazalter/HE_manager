import { reactive } from 'vue'
import axios, { CanceledError } from 'axios'
import { API_BASE_URL } from './config'
import type { User } from './types'
import { desktopBridge, desktopSession } from './desktop'
import type { DesktopSessionSnapshot } from './desktop-contract'

const AUTH_TOKEN_STORAGE_KEY = 'he_manager_token'

export const authState = reactive({
  ready: false,
  token: desktopBridge ? '' : localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || '',
  user: null as User | null,
  hasUsers: true,
  error: '',
})

// Existing Web tokens remain Web-only. Desktop identity keys are non-secret generations.
export const authIdentity = () => desktopBridge ? (authState.user ? desktopSession.generation : '') : authState.token
export const authHeaders = (): Record<string, string> => desktopBridge
  ? { 'X-HE-Generation': desktopSession.generation }
  : authState.token ? { Authorization: 'Bearer ' + authState.token } : {}
let listening = false
function applyDesktopSession(value: DesktopSessionSnapshot) {
  if (value.revision < desktopSession.revision) return
  Object.assign(desktopSession, value)
  authState.token = ''; authState.user = value.user; authState.hasUsers = value.hasUsers; authState.error = value.error
}

const applyToken = (token: string) => {
  authState.token = token
  if (token) {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token)
    axios.defaults.headers.common.Authorization = `Bearer ${token}`
  } else {
    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
    delete axios.defaults.headers.common.Authorization
  }
}

export const expireAuth = () => {
  if (desktopBridge) { void desktopBridge.logout().then(applyDesktopSession); return }
  applyToken(''); authState.user = null
}

axios.interceptors.request.use(config => {
  if (desktopBridge) {
    config.headers.delete('Authorization')
    if (!config.headers.has('X-HE-Generation')) config.headers.set('X-HE-Generation', desktopSession.generation)
    return config
  }
  const token = authState.token || localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || ''
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

axios.interceptors.response.use(
  response => {
    if (desktopBridge && response.config.headers.get('X-HE-Generation') !== desktopSession.generation) throw new CanceledError('账号或服务器已改变')
    return response
  },
  error => {
    if (desktopBridge) {
      if (error?.config?.headers?.get('X-HE-Generation') !== desktopSession.generation) return Promise.reject(new CanceledError('账号或服务器已改变'))
      return Promise.reject(error)
    }
    const url = String(error?.config?.url || '')
    if (error?.response?.status === 401 && !url.includes('/auth/login')) {
      applyToken('')
      authState.user = null
    }
    return Promise.reject(error)
  },
)

export const initAuth = async () => {
  authState.ready = false
  authState.error = ''
  if (desktopBridge) {
    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
    delete axios.defaults.headers.common.Authorization
    if (!listening) { desktopBridge.onSessionChanged(applyDesktopSession); listening = true }
    try { applyDesktopSession(await desktopBridge.authentication()) }
    catch { authState.user = null; authState.error = '无法检查登录状态，请重新连接服务器。' }
    authState.ready = true
    return
  }
  applyToken(authState.token)
  try {
    const status = await axios.get(`${API_BASE_URL}/auth/status`, { timeout: 5000 })
    authState.hasUsers = Boolean(status.data.has_users)
  } catch (err: any) {
    applyToken('')
    authState.user = null
    authState.error = err.code === 'ECONNABORTED'
      ? '连接后端超时，请确认 HE Manager 服务正在运行。'
      : '无法连接后端，请确认 HE Manager 服务正在运行。'
    authState.ready = true
    return
  }

  if (authState.token) {
    try {
      const me = await axios.get(`${API_BASE_URL}/auth/me`, { timeout: 5000 })
      authState.user = me.data
    } catch (err: any) {
      applyToken('')
      authState.user = null
      if (err.response?.status !== 401) {
        authState.error = err.code === 'ECONNABORTED'
          ? '连接后端超时，请确认 HE Manager 服务正在运行。'
          : '无法连接后端，请确认 HE Manager 服务正在运行。'
      }
    }
  }

  authState.ready = true
}

export const login = async (username: string, password: string) => {
  if (desktopBridge) { applyDesktopSession(await desktopBridge.login({ username, password })); return }
  const res = await axios.post(`${API_BASE_URL}/auth/login`, { username, password })
  applyToken(res.data.access_token)
  authState.user = res.data.user
  authState.hasUsers = true
}

export const bootstrapAdmin = async (username: string, password: string) => {
  if (desktopBridge) { applyDesktopSession(await desktopBridge.login({ username, password, bootstrap: true })); return }
  const res = await axios.post(`${API_BASE_URL}/auth/bootstrap`, { username, password, is_admin: true })
  applyToken(res.data.access_token)
  authState.user = res.data.user
  authState.hasUsers = true
}

export const logout = async () => {
  if (desktopBridge) { applyDesktopSession(await desktopBridge.logout()); return }
  try {
    if (authState.token) await axios.post(`${API_BASE_URL}/auth/logout`, {})
  } catch {
    // Best-effort server-side revocation; local logout should always work.
  }
  applyToken('')
  authState.user = null
  try {
    const status = await axios.get(`${API_BASE_URL}/auth/status`, { timeout: 5000 })
    authState.hasUsers = Boolean(status.data.has_users)
    authState.error = ''
  } catch (err: any) {
    authState.hasUsers = true
    authState.error = err.code === 'ECONNABORTED'
      ? '连接后端超时，请确认 HE Manager 服务正在运行。'
      : '无法连接后端，请确认 HE Manager 服务正在运行。'
  }
}

export const retryAuth = async () => {
  if (!desktopBridge) return initAuth()
  try { applyDesktopSession(await desktopBridge.restoreLogin()) }
  catch { authState.error = '无法连接服务器，请检查网络后重试。' }
}
