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
  authState.ready = !value.restoring
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
  authEpoch++; applyToken(''); authState.user = null; authState.ready = true
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
      const headers = error?.config?.headers
      const reqAuth = headers ? (typeof headers.get === 'function' ? headers.get('Authorization') : headers.Authorization || headers.authorization) : undefined
      const currentAuth = authState.token ? `Bearer ${authState.token}` : ''
      if (!reqAuth || !currentAuth || reqAuth === currentAuth) {
        applyToken('')
        authState.user = null
      }
    }
    return Promise.reject(error)
  },
)

let authEpoch = 0

export const initAuth = async () => {
  const epoch = ++authEpoch
  authState.ready = false
  authState.error = ''
  if (desktopBridge) {
    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
    delete axios.defaults.headers.common.Authorization
    if (!listening) { desktopBridge.onSessionChanged(applyDesktopSession); listening = true }
    try {
      const session = await desktopBridge.authentication()
      if (epoch === authEpoch) applyDesktopSession(session)
    } catch {
      if (epoch === authEpoch) {
        authState.user = null
        authState.error = '无法检查登录状态，请重新连接服务器。'
      }
    }
    if (epoch === authEpoch) authState.ready = !desktopSession.restoring
    return
  }

  const token = authState.token || localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || ''
  applyToken(token)
  const current = () => epoch === authEpoch && authState.token === token
  const connectionError = (err: any) => err.code === 'ECONNABORTED'
    ? '连接后端超时，请确认 HE Manager 服务正在运行。'
    : '无法连接后端，请确认 HE Manager 服务正在运行。'
  try {
    const status = await axios.get(`${API_BASE_URL}/auth/status`, { timeout: 5000 })
    if (!current()) return
    authState.hasUsers = Boolean(status.data.has_users)
    if (token) {
      try {
        const me = await axios.get(`${API_BASE_URL}/auth/me`, { timeout: 5000 })
        if (current()) authState.user = me.data
      } catch (err: any) {
        if (epoch !== authEpoch) return
        // The response interceptor can already have cleared this token on 401.
        if (!current() && !(err.response?.status === 401 && !authState.token)) return
        authState.user = null
        if (err.response?.status === 401) applyToken('')
        else authState.error = connectionError(err)
      }
    } else {
      authState.user = null
    }
  } catch (err: any) {
    if (current()) {
      authState.user = null
      authState.error = connectionError(err)
    }
  } finally {
    if (epoch === authEpoch) authState.ready = true
  }
}

export const login = async (username: string, password: string) => {
  if (desktopBridge) { applyDesktopSession(await desktopBridge.login({ username, password })); return }
  const res = await axios.post(`${API_BASE_URL}/auth/login`, { username, password })
  authEpoch++
  applyToken(res.data.access_token)
  authState.user = res.data.user
  authState.hasUsers = true
  authState.ready = true
  authState.error = ''
}

export const bootstrapAdmin = async (username: string, password: string) => {
  if (desktopBridge) { applyDesktopSession(await desktopBridge.login({ username, password, bootstrap: true })); return }
  const res = await axios.post(`${API_BASE_URL}/auth/bootstrap`, { username, password, is_admin: true })
  authEpoch++
  applyToken(res.data.access_token)
  authState.user = res.data.user
  authState.hasUsers = true
  authState.ready = true
  authState.error = ''
}

export const logout = async () => {
  const epoch = ++authEpoch
  if (desktopBridge) { applyDesktopSession(await desktopBridge.logout()); return }
  try {
    if (authState.token) await axios.post(`${API_BASE_URL}/auth/logout`, {})
  } catch {
    // Best-effort server-side revocation; local logout should always work.
  }
  if (epoch !== authEpoch) return
  applyToken('')
  authState.user = null
  authState.ready = true
  authState.error = ''
  try {
    const status = await axios.get(`${API_BASE_URL}/auth/status`, { timeout: 5000 })
    if (epoch !== authEpoch) return
    authState.hasUsers = Boolean(status.data.has_users)
  } catch (err: any) {
    if (epoch !== authEpoch) return
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
