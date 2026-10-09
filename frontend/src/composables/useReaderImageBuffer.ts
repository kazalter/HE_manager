import { reactive } from 'vue'

export interface ReaderImageState {
  status: 'queued' | 'loading' | 'ready' | 'error'
  width?: number
  height?: number
}

/** Fetch and decode a small window before it reaches the reader viewport. */
export function useReaderImageBuffer(onReady: (update: () => void) => void = update => update()) {
  const states = reactive(new Map<string, ReaderImageState>())
  const decoded = new Map<string, HTMLImageElement>()
  const inFlight = new Map<string, { cancel: () => void }>()
  let queue: string[] = []
  let active = 0
  let generation = 0
  let disposed = false
  let wanted = new Set<string>()
  let visible = new Set<string>()

  const pump = () => {
    while (!disposed && queue.length) {
      if (active >= 3) {
        const visibleQueued = queue.some(url => visible.has(url) && states.get(url)?.status === 'queued')
        if (!visibleQueued) break
        // A slow speculative image must never hold the visible page or its retry hostage.
        const speculative = [...inFlight.entries()].reverse().find(([url]) => !visible.has(url))
        if (!speculative) break
        speculative[1].cancel()
      }
      const url = queue.shift()!
      const state = states.get(url)
      if (!state || state.status !== 'queued') continue
      state.status = 'loading'
      active++
      const epoch = generation
      const img = new Image()
      img.decoding = 'async'
      let finished = false
      const finish = (success: boolean) => {
        if (finished || epoch !== generation || disposed) return
        finished = true
        inFlight.delete(url)
        active--
        onReady(() => {
          states.set(url, success
            ? { status: 'ready', width: img.naturalWidth, height: img.naturalHeight }
            : { status: 'error' })
        })
        if (success && wanted.has(url)) decoded.set(url, img)
        pump()
      }
      inFlight.set(url, { cancel: () => {
        if (finished) return
        finished = true
        inFlight.delete(url)
        active--
        img.onload = null
        img.onerror = null
        img.src = ''
        if (wanted.has(url)) {
          states.set(url, { status: 'queued' })
          if (!queue.includes(url)) queue.push(url)
        } else {
          states.delete(url)
        }
      } })
      img.onload = async () => {
        if (finished) return
        // A loaded file can still need decoding. Keep its decoded bitmap nearby.
        try { await img.decode() } catch { /* Loaded formats without decode support remain usable. */ }
        finish(true)
      }
      img.onerror = () => finish(false)
      img.src = url
    }
  }

  const requestWindow = (urls: string[], visibleCount = 1) => {
    wanted = new Set(urls)
    visible = new Set(urls.slice(0, visibleCount))
    for (const [url, request] of inFlight) if (!wanted.has(url)) request.cancel()
    for (const url of decoded.keys()) if (!wanted.has(url)) decoded.delete(url)
    for (const [url, state] of states) {
      if (state.status === 'queued' && !wanted.has(url)) states.delete(url)
    }
    // Put the current viewport ahead of obsolete speculative work after a jump.
    queue = urls.filter(url => {
      if (states.has(url)) return states.get(url)?.status === 'queued'
      states.set(url, { status: 'queued' })
      return true
    })
    pump()
  }
  const retry = (url: string) => {
    if (states.get(url)?.status !== 'error') return
    states.set(url, { status: 'queued' })
    visible.add(url)
    queue.unshift(url)
    pump()
  }
  const clear = () => {
    generation++
    wanted.clear()
    visible.clear()
    for (const request of inFlight.values()) request.cancel()
    active = 0
    queue = []
    states.clear()
    decoded.clear()
  }
  const dispose = () => { clear(); disposed = true }
  return { states, requestWindow, retry, clear, dispose }
}
