/** Failed image load; `status` is the HTTP status, or null for a stall / network error. */
export class PawchiveImageError extends Error {
  readonly status: number | null

  constructor(status: number | null, message: string) {
    super(message)
    this.name = 'PawchiveImageError'
    this.status = status
  }
}

export interface ImageFetchOptions {
  signal?: AbortSignal
  /** Abort only when no bytes arrive for this long; slow but moving downloads continue. */
  idleMs: number
  /** Fraction 0..1 when the size is known, otherwise null. */
  onProgress?: (progress: number | null) => void
}

const abortError = () => new DOMException('Aborted', 'AbortError')

export const isAbortError = (error: unknown) =>
  error instanceof DOMException && error.name === 'AbortError'

/**
 * Fetch an image as a Blob with an inactivity timeout instead of a total one,
 * so a 20 MB original over a slow proxy is not killed while it is still arriving.
 */
export async function fetchImageBlob(url: string, options: ImageFetchOptions): Promise<Blob> {
  const { signal, idleMs, onProgress } = options
  if (signal?.aborted) throw abortError()
  const request = new AbortController()
  let stalled = false
  let idleTimer: number | undefined
  const armIdle = () => {
    window.clearTimeout(idleTimer)
    idleTimer = window.setTimeout(() => { stalled = true; request.abort() }, idleMs)
  }
  const forwardAbort = () => request.abort()
  signal?.addEventListener('abort', forwardAbort)
  armIdle()
  try {
    const response = await fetch(url, { signal: request.signal })
    if (response.status !== 200) throw new PawchiveImageError(response.status, `HTTP ${response.status}`)
    const type = response.headers.get('content-type') || ''
    if (!type.startsWith('image/')) throw new PawchiveImageError(response.status, 'not an image')
    const declared = Number(response.headers.get('content-length'))
    const total = Number.isFinite(declared) && declared > 0 ? declared : 0
    if (!response.body) {
      const blob = await response.blob()
      onProgress?.(1)
      return blob
    }
    const reader = response.body.getReader()
    const parts: Uint8Array[] = []
    let loaded = 0
    onProgress?.(total ? 0 : null)
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      armIdle()
      parts.push(value)
      loaded += value.byteLength
      onProgress?.(total ? Math.min(1, loaded / total) : null)
    }
    if (total && loaded !== total) throw new PawchiveImageError(null, 'incomplete image')
    return new Blob(parts as BlobPart[], { type })
  } catch (error) {
    if (signal?.aborted) throw abortError()
    if (error instanceof PawchiveImageError) throw error
    throw new PawchiveImageError(null, stalled ? 'stalled' : 'network error')
  } finally {
    window.clearTimeout(idleTimer)
    signal?.removeEventListener('abort', forwardAbort)
  }
}
