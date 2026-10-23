import { computed, nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'

/** Content-only pinch zoom; native one-finger scrolling remains intact at 1x. */
export function useWebtoonZoom(viewport: Ref<HTMLDivElement | null>, content: Ref<HTMLDivElement | null>) {
  const scale = ref(1), translateX = ref(0), contentHeight = ref(0), isInteracting = ref(false)
  let previousDistance = 0, previousX = 0, previousY = 0
  let gesturePinched = false
  let panX = 0, panY = 0, panTx = 0, panScroll = 0
  let rect: DOMRect | undefined, pendingScroll: number | null = null
  let revision = 0, disposed = false
  let observer: ResizeObserver | undefined
  const measure = () => { contentHeight.value = content.value?.offsetHeight || 0 }
  watch(content, element => {
    observer?.disconnect(); observer = undefined
    if (!element) { contentHeight.value = 0; return }
    measure()
    if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(measure); observer.observe(element) }
  }, { flush: 'post' })
  const clampX = (x: number, zoom: number) => Math.max((viewport.value?.clientWidth || 0) * (1 - zoom), Math.min(0, x))
  const setScroll = (top: number) => {
    if (!viewport.value) { pendingScroll = null; revision++; return }
    const maximum = Math.max(0, contentHeight.value * scale.value - (viewport.value?.clientHeight || 0))
    const bounded = Math.max(0, Math.min(maximum, top))
    pendingScroll = bounded
    const version = ++revision
    // The scaled scroll extent must be committed before setting scrollTop.
    void nextTick(() => {
      if (disposed || version !== revision || !viewport.value) return
      viewport.value.scrollTop = bounded
      pendingScroll = null
    })
  }
  const midpoint = (touches: TouchList) => ({
    x: (touches[0]!.clientX + touches[1]!.clientX) / 2,
    y: (touches[0]!.clientY + touches[1]!.clientY) / 2,
    distance: Math.hypot(touches[0]!.clientX - touches[1]!.clientX, touches[0]!.clientY - touches[1]!.clientY),
  })
  const startPan = (touch: Touch) => {
    panX = touch.clientX; panY = touch.clientY; panTx = translateX.value
    panScroll = pendingScroll ?? viewport.value?.scrollTop ?? 0
  }
  const onTouchStart = (event: TouchEvent) => {
    rect = viewport.value?.getBoundingClientRect(); measure()
    if (event.touches.length >= 2) {
      gesturePinched = true
      const point = midpoint(event.touches)
      previousDistance = Math.max(1, point.distance); previousX = point.x; previousY = point.y
      isInteracting.value = true
      if (event.cancelable) event.preventDefault()
    } else if (event.touches[0]) { gesturePinched = false; startPan(event.touches[0]); isInteracting.value = scale.value > 1 }
  }
  const onTouchMove = (event: TouchEvent) => {
    if (!viewport.value || !rect) return
    if (event.touches.length >= 2 && previousDistance) {
      if (event.cancelable) event.preventDefault()
      const point = midpoint(event.touches)
      const nextScale = Math.max(1, Math.min(5, scale.value * point.distance / previousDistance))
      const ratio = nextScale / scale.value
      const scroll = pendingScroll ?? viewport.value.scrollTop
      const nextTop = (scroll + previousY - rect.top) * ratio - (point.y - rect.top)
      translateX.value = clampX(point.x - rect.left - (previousX - rect.left - translateX.value) * ratio, nextScale)
      scale.value = nextScale
      setScroll(nextTop)
      previousDistance = Math.max(1, point.distance); previousX = point.x; previousY = point.y
    } else if (event.touches.length === 1 && (scale.value > 1 || gesturePinched)) {
      if (event.cancelable) event.preventDefault()
      translateX.value = clampX(panTx + event.touches[0]!.clientX - panX, scale.value)
      setScroll(panScroll - (event.touches[0]!.clientY - panY))
    }
  }
  const onTouchEnd = (event: TouchEvent) => {
    if (event.type !== 'touchcancel' && event.touches.length >= 2) { onTouchStart(event); return }
    previousDistance = 0
    isInteracting.value = event.type !== 'touchcancel' && event.touches.length > 0 && (scale.value > 1 || gesturePinched)
    if (event.touches[0]) startPan(event.touches[0])
    if (!event.touches.length || event.type === 'touchcancel') gesturePinched = false
  }
  const reset = () => {
    const top = (pendingScroll ?? viewport.value?.scrollTop ?? 0) / scale.value
    scale.value = 1; translateX.value = 0; previousDistance = 0; isInteracting.value = false; gesturePinched = false
    setScroll(top)
  }
  onBeforeUnmount(() => { disposed = true; revision++; observer?.disconnect() })
  return { scale, translateX, contentHeight, isInteracting, measure, reset, onTouchStart, onTouchMove, onTouchEnd,
    spaceStyle: computed(() => ({ height: contentHeight.value ? `${contentHeight.value * scale.value}px` : undefined })),
    contentStyle: computed(() => ({
      position: contentHeight.value ? 'absolute' as const : 'relative' as const,
      transformOrigin: 'top left',
      transform: scale.value === 1 ? undefined : `translate3d(${translateX.value}px, 0, 0) scale(${scale.value})`,
    })),
  }
}
