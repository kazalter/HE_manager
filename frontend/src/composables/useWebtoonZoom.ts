import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

/** Only a pinch owns scrolling; independent one-finger gestures stay native. */
export function useWebtoonZoom(viewport: Ref<HTMLDivElement | null>, content: Ref<HTMLDivElement | null>) {
  const scale = ref(1), translateX = ref(0), contentHeight = ref(0), isInteracting = ref(false)
  let previousDistance = 0, previousX = 0, previousY = 0
  let gesturePinched = false, touching = false
  let panX = 0, panY = 0, panTx = 0, panScroll = 0
  let rect: DOMRect | undefined
  let observer: ResizeObserver | undefined
  let activeTarget: HTMLDivElement | null = null
  const stopBlockingMoves = () => {
    activeTarget?.removeEventListener('touchmove', onTouchMove)
    activeTarget = null
  }
  const startBlockingMoves = () => {
    stopBlockingMoves()
    activeTarget = viewport.value
    activeTarget?.addEventListener('touchmove', onTouchMove, { passive: false })
  }
  // Styles are written directly. Binding them in the reader template would
  // re-render every page of the column on each touchmove of a pinch or pan.
  const render = () => {
    const element = content.value
    if (!element) return
    const zoomed = scale.value > 1 && contentHeight.value > 0
    // At 1x the column stays in normal flow, without a measured height shim.
    const space = element.parentElement
    if (space) space.style.height = zoomed ? `${contentHeight.value * scale.value}px` : ''
    element.style.position = zoomed ? 'absolute' : ''
    element.style.transformOrigin = 'top left'
    element.style.transform = scale.value === 1 ? '' : `translate(${translateX.value}px, 0px) scale(${scale.value})`
    // Composite only while fingers move it; dropping the hint re-rasterizes sharply.
    element.style.willChange = isInteracting.value || (touching && scale.value > 1) ? 'transform' : ''
  }
  const measure = () => {
    contentHeight.value = content.value?.offsetHeight || 0
    if (scale.value > 1) render()
  }
  watch([content, () => scale.value > 1], ([element, zoomed]) => {
    observer?.disconnect(); observer = undefined
    if (!element || !zoomed) return
    measure()
    if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(measure); observer.observe(element) }
  }, { flush: 'post' })
  watch(content, render, { flush: 'post' })
  watch(viewport, stopBlockingMoves, { flush: 'sync' })
  const clampX = (x: number, zoom: number) => Math.max((viewport.value?.clientWidth || 0) * (1 - zoom), Math.min(0, x))
  // The scaled extent is already rendered, so the scroll position can follow in the same frame.
  const setScroll = (top: number) => {
    const element = viewport.value
    if (!element) return
    const maximum = Math.max(0, contentHeight.value * scale.value - element.clientHeight)
    element.scrollTop = Math.max(0, Math.min(maximum, top))
  }
  const midpoint = (touches: TouchList) => ({
    x: (touches[0]!.clientX + touches[1]!.clientX) / 2,
    y: (touches[0]!.clientY + touches[1]!.clientY) / 2,
    distance: Math.hypot(touches[0]!.clientX - touches[1]!.clientX, touches[0]!.clientY - touches[1]!.clientY),
  })
  const startPan = (touch: Touch) => {
    panX = touch.clientX; panY = touch.clientY; panTx = translateX.value
    panScroll = viewport.value?.scrollTop ?? 0
  }
  const onTouchStart = (event: TouchEvent) => {
    if (event.touches.length >= 2) {
      rect = viewport.value?.getBoundingClientRect(); measure()
      gesturePinched = true; touching = true
      const point = midpoint(event.touches)
      previousDistance = Math.max(1, point.distance); previousX = point.x; previousY = point.y
      isInteracting.value = true
      render()
      // touchstart itself is passive. Only moves during this pinch can block
      // native scrolling; remove this listener as soon as all fingers lift.
      startBlockingMoves()
    } else if (event.touches[0]) {
      gesturePinched = false; isInteracting.value = false
      stopBlockingMoves()
      if (scale.value > 1) {
        touching = true
        startPan(event.touches[0])
        render()
      }
    }
  }
  const onTouchMove = (event: TouchEvent) => {
    if (!gesturePinched) {
      // Native pan-y retains vertical inertia even when the column is enlarged.
      if (scale.value > 1 && event.touches.length === 1) {
        translateX.value = clampX(panTx + event.touches[0]!.clientX - panX, scale.value)
        render()
      }
      return
    }
    if (!viewport.value || !rect) return
    if (event.touches.length >= 2 && previousDistance) {
      if (event.cancelable) event.preventDefault()
      const point = midpoint(event.touches)
      const nextScale = Math.max(1, Math.min(5, scale.value * point.distance / previousDistance))
      const ratio = nextScale / scale.value
      const nextTop = (viewport.value.scrollTop + previousY - rect.top) * ratio - (point.y - rect.top)
      translateX.value = clampX(point.x - rect.left - (previousX - rect.left - translateX.value) * ratio, nextScale)
      scale.value = nextScale
      render()
      setScroll(nextTop)
      previousDistance = Math.max(1, point.distance); previousX = point.x; previousY = point.y
    } else if (event.touches.length === 1) {
      if (event.cancelable) event.preventDefault()
      translateX.value = clampX(panTx + event.touches[0]!.clientX - panX, scale.value)
      render()
      setScroll(panScroll - (event.touches[0]!.clientY - panY))
    }
  }
  // The permanently installed move observer must never cancel native scrolling.
  const onPassiveTouchMove = (event: TouchEvent) => { if (!gesturePinched) onTouchMove(event) }
  const onTouchEnd = (event: TouchEvent) => {
    if (event.type !== 'touchcancel' && event.touches.length >= 2) { onTouchStart(event); return }
    previousDistance = 0
    isInteracting.value = event.type !== 'touchcancel' && event.touches.length > 0 && gesturePinched
    if (event.touches[0]) startPan(event.touches[0])
    if (!event.touches.length || event.type === 'touchcancel') {
      gesturePinched = false; touching = false
      stopBlockingMoves()
    }
    render()
  }
  const reset = () => {
    isInteracting.value = false; gesturePinched = false; touching = false; previousDistance = 0
    stopBlockingMoves()
    if (scale.value === 1 && translateX.value === 0) { render(); return }
    const top = (viewport.value?.scrollTop ?? 0) / scale.value
    scale.value = 1; translateX.value = 0
    render()
    setScroll(top)
  }
  onBeforeUnmount(() => { observer?.disconnect(); stopBlockingMoves() })
  return { scale, translateX, contentHeight, isInteracting, measure, reset, onTouchStart, onTouchMove, onPassiveTouchMove, onTouchEnd }
}
