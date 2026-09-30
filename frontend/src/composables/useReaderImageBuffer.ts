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
  let queue: string[] = []
  let active = 0
  let generation = 0
  let disposed = false
  let wanted = new Set<string>()

  const pump = () => {
    while (!disposed && active < 3 && queue.length) {
      const url = queue.shift()!
      const state = states.get(url)
      if (!state || state.status !== 'queued') continue
      state.status = 'loading'
      active++
      const epoch = generation
      const img = new Image()
      img.decoding = 'async'
      const finish = (success: boolean) => {
        if (epoch !== generation || disposed) return
        active--
        onReady(() => {
          states.set(url, success
            ? { status: 'ready', width: img.naturalWidth, height: img.naturalHeight }
            : { status: 'error' })
        })
        if (success && wanted.has(url)) decoded.set(url, img)
        pump()
      }
      img.onload = async () => {
        // A loaded file can still need decoding. Keep its decoded bitmap nearby.
        try { await img.decode() } catch { /* Loaded formats without decode support remain usable. */ }
        finish(true)
      }
      img.onerror = () => finish(false)
      img.src = url
    }
  }

  const requestWindow = (urls: string[]) => {
    wanted = new Set(urls)
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
    queue.unshift(url)
    pump()
  }
  const clear = () => {
    generation++
    active = 0
    queue = []
    states.clear()
    decoded.clear()
    wanted.clear()
  }
  const dispose = () => { clear(); disposed = true }
  return { states, requestWindow, retry, clear, dispose }
}
