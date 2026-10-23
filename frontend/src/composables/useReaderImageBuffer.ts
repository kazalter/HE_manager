import { reactive, shallowReactive } from 'vue'

export const READER_DECODE_CACHE_BYTES = 96 * 1024 * 1024
export const READER_DECODE_CACHE_IMAGES = 24

export interface ReaderImageState {
  status: 'queued' | 'loading' | 'ready' | 'error'
  width?: number
  height?: number
}

/** Fetch and decode a small window before it reaches the reader viewport. */
export function useReaderImageBuffer(
  onReady: (update: () => void) => void = update => update(),
  limits: { maxBytes?: number; maxImages?: number } = {},
) {
  const states = reactive(new Map<string, ReaderImageState>())
  const decoded = shallowReactive(new Map<string, { image: HTMLImageElement; bytes: number }>())
  const loading = shallowReactive(new Set<string>())
  const inFlight = new Map<string, { image: HTMLImageElement; cancel: () => void }>()
  const maxBytes = limits.maxBytes ?? READER_DECODE_CACHE_BYTES
  const maxImages = limits.maxImages ?? READER_DECODE_CACHE_IMAGES
  let decodedBytes = 0
  let windowKey = ''
  let queue: string[] = []
  let active = 0
  let generation = 0
  let disposed = false
  let wanted = new Set<string>()
  let visible = new Set<string>()

  const trimDecoded = () => {
    while (decoded.size > maxImages || decodedBytes > maxBytes) {
      // Preserve on-screen pixels. Prefer old history, then the farthest prefetch.
      const history = [...decoded.keys()].find(url => !wanted.has(url) && !visible.has(url))
      const speculative = [...wanted].reverse().find(url => decoded.has(url) && !visible.has(url))
      const url = history ?? speculative
      if (!url) break // One very large visible page can exceed the soft budget.
      decodedBytes -= decoded.get(url)!.bytes
      decoded.delete(url)
    }
  }
  const needsLoad = (url: string) => !inFlight.has(url) && !decoded.has(url)
    && (states.get(url)?.status === 'queued' || states.get(url)?.status === 'ready')

  const pump = () => {
    while (!disposed && queue.length) {
      if (active >= 3) {
        const visibleQueued = queue.some(url => visible.has(url) && needsLoad(url))
        if (!visibleQueued) break
        // A slow speculative image must never hold the visible page or its retry hostage.
        const speculative = [...inFlight.entries()].reverse().find(([url]) => !visible.has(url))
        if (!speculative) break
        speculative[1].cancel()
      }
      const url = queue.shift()!
      const state = states.get(url)
      if (!state || !needsLoad(url)) continue
      // A downloaded page can need decoding again after bitmap eviction. Keep
      // its dimensions and HTTP-cache identity, rather than treating it as new.
      const previousReady = state.status === 'ready' ? { ...state } : undefined
      if (!previousReady) state.status = 'loading'
      loading.add(url)
      active++
      const epoch = generation
      const img = new Image()
      img.decoding = 'async'
      img.fetchPriority = visible.has(url) ? 'high' : 'low'
      let finished = false
      const finish = (success: boolean) => {
        if (finished || epoch !== generation || disposed) return
        finished = true
        inFlight.delete(url)
        loading.delete(url)
        active--
        onReady(() => {
          if (success) {
            states.set(url, { status: 'ready', width: img.naturalWidth, height: img.naturalHeight })
            const bytes = Math.max(1, img.naturalWidth * img.naturalHeight * 4)
            decoded.set(url, { image: img, bytes }); decodedBytes += bytes
            trimDecoded()
          } else states.set(url, { status: 'error' })
        })
        pump()
      }
      inFlight.set(url, { image: img, cancel: () => {
        if (finished) return
        finished = true
        inFlight.delete(url)
        loading.delete(url)
        active--
        img.onload = null
        img.onerror = null
        img.src = ''
        if (previousReady || wanted.has(url)) {
          states.set(url, previousReady ?? { status: 'queued' })
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
    const key = JSON.stringify([visibleCount, urls])
    if (key === windowKey || disposed) return
    windowKey = key
    wanted = new Set(urls)
    visible = new Set(urls.slice(0, visibleCount))
    for (const [url, request] of inFlight) {
      if (!wanted.has(url)) request.cancel()
      else request.image.fetchPriority = visible.has(url) ? 'high' : 'low'
    }
    // Touch in reverse priority order so the viewport is most recently used.
    for (const url of [...urls].reverse()) {
      const cached = decoded.get(url)
      if (cached) { decoded.delete(url); decoded.set(url, cached) }
    }
    trimDecoded()
    for (const [url, state] of states) {
      if (state.status === 'queued' && !wanted.has(url)) states.delete(url)
    }
    // Put the current viewport ahead of obsolete speculative work after a jump.
    queue = urls.filter(url => {
      if (!states.has(url)) states.set(url, { status: 'queued' })
      return needsLoad(url)
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
    windowKey = ''
    wanted.clear()
    visible.clear()
    for (const request of inFlight.values()) request.cancel()
    active = 0
    queue = []
    states.clear()
    decoded.clear()
    decodedBytes = 0
    loading.clear()
  }
  const dispose = () => { clear(); disposed = true }
  return { states, requestWindow, retry, clear, dispose,
    isDecoded: (url: string) => decoded.has(url),
    isResident: (url: string) => decoded.has(url) || loading.has(url),
  }
}
