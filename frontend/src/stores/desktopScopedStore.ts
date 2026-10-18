import { shallowRef, watch } from 'vue'
import axios, { CanceledError, type AxiosStatic } from 'axios'
import { authHeaders, authIdentity, authState } from '../auth'
import { desktopBridge, desktopSession } from '../desktop'

export interface StoreScope {
  http: Pick<AxiosStatic, 'get' | 'post' | 'patch' | 'delete' | 'isCancel'>
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
  active: () => boolean
  clearInterval: typeof window.clearInterval
  setInterval: typeof window.setInterval
}
// Desktop singleton stores get a fresh closure per identity. An old async catch
// can only change its discarded closure, and its HTTP/storage/timers remain bound
// to the identity that created it. Web retains its existing singleton behavior.
export function desktopScopedStore<T extends object>(factory: (scope: StoreScope) => T): T {
  const signature = () => desktopBridge ? JSON.stringify([authIdentity(), desktopSession.server, authState.user?.id]) : 'web'
  let dispose = () => {}
  let previous = ''
  const current = shallowRef<T>()
  function refresh() {
    const next = signature()
    if (current.value && next === previous) return
    dispose(); previous = next
    const identity = authIdentity(), server = desktopSession.server, userId = authState.user?.id
    const controller = new AbortController(), timers = new Set<number>()
    let closed = false
    const active = () => !closed && (!desktopBridge || next === signature())
    const client = desktopBridge ? axios.create({ headers: authHeaders(), timeout: 15000 }) : axios
    if (desktopBridge) {
      client.interceptors.request.use(config => {
        if (!active() || !identity) throw new CanceledError('账号或服务器已改变')
        config.signal = config.signal ? AbortSignal.any([controller.signal, config.signal as AbortSignal]) : controller.signal
        return config
      })
      client.interceptors.response.use(response => {
        if (!active()) throw new CanceledError('账号或服务器已改变')
        return response
      })
    }
    const keyFor = (key: string) => desktopBridge ? `${key}:desktop:${encodeURIComponent(JSON.stringify([server, userId]))}` : key
    const storage = {
      getItem: (key: string) => active() && (!desktopBridge || !!userId) ? localStorage.getItem(keyFor(key)) : null,
      setItem: (key: string, value: string) => { if (active() && (!desktopBridge || !!userId)) localStorage.setItem(keyFor(key), value) },
      removeItem: (key: string) => { if (active() && (!desktopBridge || !!userId)) localStorage.removeItem(keyFor(key)) },
    }
    const scopedInterval: typeof window.setInterval = (handler, timeout, ...args) => {
      if (!active()) return 0
      const timer = window.setInterval(() => {
        if (!active()) { window.clearInterval(timer); timers.delete(timer); return }
        if (typeof handler === 'function') handler(...args)
      }, timeout)
      timers.add(timer); return timer
    }
    dispose = () => { closed = true; controller.abort(); for (const timer of timers) window.clearInterval(timer); timers.clear() }
    const clearInterval: typeof window.clearInterval = timer => { window.clearInterval(timer); if (timer !== undefined) timers.delete(timer) }
    current.value = factory({ http: Object.assign(client, { isCancel: axios.isCancel }), storage, active, clearInterval, setInterval: scopedInterval })
  }
  refresh()
  if (desktopBridge) watch(signature, refresh)
  return new Proxy({} as T, { get(_target, key) { refresh(); return Reflect.get(current.value!, key) } })
}
