import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

// Per-millisecond velocity retention for a released pan of the enlarged column.
const FLING_DECAY = 0.997
const FLING_MIN_SPEED = 0.12

/**
 * At 1x the column scrolls natively and only a pinch is handled here. Once
 * enlarged, browsers lock a native touch scroll to the axis it starts on
 * (pan-y suppresses vertical after a sideways start; Chrome also rails steep
 * diagonals), so both axes of a drag are driven here, together, with momentum.
 */
export function useWebtoonZoom(viewport: Ref<HTMLDivElement | null>, content: Ref<HTMLDivElement | null>) {
  const scale = ref(1), contentHeight = ref(0), isInteracting = ref(false)
  let baseWidth = 0, viewHeight = 0
  let previousDistance = 0, previousX = 0, previousY = 0
  let gesturePinched = false, panning = false
  let panX = 0, panY = 0, panLeft = 0, panTop = 0
  // Unrounded positions last written, since browsers may round scrollLeft/scrollTop.
  let writtenLeft = 0, writtenTop = 0
  let samples: Array<[number, number, number]> = []
  let flingRaf: number | null = null
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
  const stopFling = () => {
    if (flingRaf !== null) cancelAnimationFrame(flingRaf)
    flingRaf = null
  }
  // Styles are written directly. Binding them in the reader template would
  // re-render every page of the column on each touchmove of a pinch.
  const render = () => {
    const scroller = viewport.value, element = content.value
    const zoomed = scale.value > 1
    if (scroller) scroller.style.touchAction = zoomed ? 'none' : 'pan-y'
    if (!element) return
    // At 1x the column stays in normal flow, without a measured extent shim.
    const sized = zoomed && contentHeight.value > 0 && baseWidth > 0
    const space = element.parentElement
    if (space) {
      space.style.width = sized ? `${baseWidth * scale.value}px` : ''
      space.style.height = sized ? `${contentHeight.value * scale.value}px` : ''
    }
    element.style.position = sized ? 'absolute' : ''
    element.style.width = sized ? `${baseWidth}px` : ''
    element.style.transformOrigin = 'top left'
    element.style.transform = scale.value === 1 ? '' : `scale(${scale.value})`
    // Composite only while a pinch rescales it; at rest it is painted sharply.
    element.style.willChange = isInteracting.value ? 'transform' : ''
  }
  const measure = () => {
    contentHeight.value = content.value?.offsetHeight || 0
    baseWidth = viewport.value?.clientWidth || 0
    viewHeight = viewport.value?.clientHeight || 0
    if (scale.value > 1) render()
  }
  watch([content, viewport, () => scale.value > 1], ([element, scroller, zoomed]) => {
    observer?.disconnect(); observer = undefined
    if (!element || !zoomed) return
    measure()
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(measure)
      observer.observe(element)
      if (scroller) observer.observe(scroller)
    }
  }, { flush: 'post' })
  watch(content, render, { flush: 'post' })
  watch(viewport, () => { stopBlockingMoves(); stopFling() }, { flush: 'sync' })
  // Bounds come from the last measurement, so a drag never forces a layout read.
  const setScroll = (left: number, top: number) => {
    const scroller = viewport.value
    if (!scroller) return
    writtenLeft = Math.max(0, Math.min(Math.max(0, baseWidth * (scale.value - 1)), left))
    writtenTop = Math.max(0, Math.min(Math.max(0, contentHeight.value * scale.value - viewHeight), top))
    scroller.scrollLeft = writtenLeft
    scroller.scrollTop = writtenTop
  }
  // Prefer the exact value written last unless the scroller has since moved.
  const currentScroll = (scroller: HTMLDivElement) => ({
    left: Math.abs(scroller.scrollLeft - writtenLeft) < 1 ? writtenLeft : scroller.scrollLeft,
    top: Math.abs(scroller.scrollTop - writtenTop) < 1 ? writtenTop : scroller.scrollTop,
  })
  const midpoint = (touches: TouchList) => ({
    x: (touches[0]!.clientX + touches[1]!.clientX) / 2,
    y: (touches[0]!.clientY + touches[1]!.clientY) / 2,
    distance: Math.hypot(touches[0]!.clientX - touches[1]!.clientX, touches[0]!.clientY - touches[1]!.clientY),
  })
  const startPan = (touch: Touch) => {
    panning = true
    panX = touch.clientX; panY = touch.clientY
    samples = []
    if (!viewport.value) return
    const scroll = currentScroll(viewport.value)
    panLeft = scroll.left; panTop = scroll.top
  }
  const pan = (touch: Touch) => {
    setScroll(panLeft - (touch.clientX - panX), panTop - (touch.clientY - panY))
    const now = performance.now()
    samples.push([now, writtenLeft, writtenTop])
    while (samples.length > 2 && now - samples[0]![0] > 100) samples.shift()
  }
  const fling = () => {
    const first = samples[0], last = samples.at(-1)
    samples = []
    const elapsed = first && last ? last[0] - first[0] : 0
    // A finger that paused before lifting should not throw the column.
    if (!first || !last || elapsed < 8 || performance.now() - last[0] > 60) return
    let vx = (last[1] - first[1]) / elapsed
    let vy = (last[2] - first[2]) / elapsed
    if (Math.hypot(vx, vy) < FLING_MIN_SPEED) return
    let previous = performance.now()
    const step = (now: number) => {
      const scroller = viewport.value
      // Stop if anything else (a page button, a resize) moved the column meanwhile.
      if (!scroller || Math.abs(scroller.scrollLeft - writtenLeft) >= 1 || Math.abs(scroller.scrollTop - writtenTop) >= 1) { flingRaf = null; return }
      const elapsedFrame = Math.min(32, Math.max(0, now - previous))
      previous = now
      const decay = Math.pow(FLING_DECAY, elapsedFrame)
      vx *= decay; vy *= decay
      const nextLeft = writtenLeft + vx * elapsedFrame, nextTop = writtenTop + vy * elapsedFrame
      setScroll(nextLeft, nextTop)
      // Stop each axis at the edge instead of sliding along it.
      if (writtenLeft !== nextLeft) vx = 0
      if (writtenTop !== nextTop) vy = 0
      flingRaf = Math.hypot(vx, vy) < 0.02 ? null : requestAnimationFrame(step)
    }
    flingRaf = requestAnimationFrame(step)
  }
  const onTouchStart = (event: TouchEvent) => {
    stopFling()
    if (event.touches.length >= 2) {
      rect = viewport.value?.getBoundingClientRect(); measure()
      gesturePinched = true; panning = false
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
      // touch-action is none while enlarged, so this drag is ours on both axes.
      if (scale.value > 1) startPan(event.touches[0])
      else panning = false
    }
  }
  const onTouchMove = (event: TouchEvent) => {
    const scroller = viewport.value
    if (!gesturePinched || !scroller || !rect) return
    if (event.touches.length >= 2 && previousDistance) {
      if (event.cancelable) event.preventDefault()
      const point = midpoint(event.touches)
      const nextScale = Math.max(1, Math.min(5, scale.value * point.distance / previousDistance))
      const ratio = nextScale / scale.value
      // Keep the content under the previous midpoint under the current one.
      const scroll = currentScroll(scroller)
      const nextLeft = (scroll.left + previousX - rect.left) * ratio - (point.x - rect.left)
      const nextTop = (scroll.top + previousY - rect.top) * ratio - (point.y - rect.top)
      scale.value = nextScale
      render()
      setScroll(nextLeft, nextTop)
      previousDistance = Math.max(1, point.distance); previousX = point.x; previousY = point.y
    } else if (event.touches.length === 1 && panning) {
      // The sequence began as a pinch, so the remaining finger cannot hand over to native scrolling.
      if (event.cancelable) event.preventDefault()
      pan(event.touches[0]!)
    }
  }
  // Installed for the whole reader; it never cancels, so 1x scrolling stays native.
  const onPassiveTouchMove = (event: TouchEvent) => {
    if (!gesturePinched && panning && event.touches.length === 1) pan(event.touches[0]!)
  }
  const onTouchEnd = (event: TouchEvent) => {
    const canceled = event.type === 'touchcancel'
    if (!canceled && event.touches.length >= 2) { onTouchStart(event); return }
    if (!canceled && event.touches[0]) {
      previousDistance = 0
      if (gesturePinched || scale.value > 1) startPan(event.touches[0])
      return
    }
    const wasPinched = gesturePinched, wasPanning = panning
    previousDistance = 0; gesturePinched = false; panning = false
    if (wasPinched) {
      isInteracting.value = false
      stopBlockingMoves()
      render()
    }
    if (wasPanning && !canceled && scale.value > 1) fling()
  }
  const reset = () => {
    stopFling()
    isInteracting.value = false; gesturePinched = false; panning = false; previousDistance = 0
    stopBlockingMoves()
    if (scale.value === 1) { render(); return }
    const top = (viewport.value ? currentScroll(viewport.value).top : 0) / scale.value
    scale.value = 1
    render()
    setScroll(0, top)
  }
  onBeforeUnmount(() => { stopFling(); observer?.disconnect(); stopBlockingMoves() })
  return { scale, contentHeight, isInteracting, measure, reset, onTouchStart, onTouchMove, onPassiveTouchMove, onTouchEnd }
}
