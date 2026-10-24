import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { animateFrames, springAtRest, stepSpring, type SpringValue } from '../utils/spring'

export interface ZoomScrollerOptions {
  /** Native scroll container. All panning while zoomed is its own scrolling. */
  scroller: Ref<HTMLElement | null>
  /** Element laid out at the zoom level, and transformed only while a zoom gesture runs. */
  content: Ref<HTMLElement | null>
  /** Lays the content out at a zoom level; every size inside it must scale linearly with it. */
  applyScale: (content: HTMLElement, scale: number) => void
  /** Content smaller than the scroller is centred (a page) rather than pinned to the start (a column). */
  centered?: boolean
  maxScale?: () => number
  doubleTapScale?: () => number
  zoomStep?: number
  /** Whether + - 0 currently zoom this surface. */
  keyboard?: () => boolean
  onSessionChange?: (active: boolean) => void
  onPinchStart?: () => void
  onDoubleTap?: () => void
  /** Horizontal flick on unzoomed content. */
  onSwipe?: (direction: -1 | 1) => void
}

const SPRING_OMEGA = 24
const TAP_SLOP = 10
const TAP_MS = 350
const DOUBLE_TAP_MS = 300
const DOUBLE_TAP_SLOP = 30
const WHEEL_SETTLE_MS = 160

interface Session {
  s0: number
  /** Touch sessions freeze native scrolling, so the fingers alone move the content. */
  frozen: boolean
  viewWidth: number
  viewHeight: number
  contentWidth: number
  contentHeight: number
  /** Content origin in scroll coordinates, and the scroll position, when the session began. */
  offsetX: number
  offsetY: number
  left: number
  top: number
  /** Scroller client origin on screen. */
  originX: number
  originY: number
  /** Live transform relative to the committed layout. */
  k: number
  tx: number
  ty: number
}

const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value))

/**
 * Pinch, double-tap, wheel and keyboard zoom for a native scroller. A zoom
 * gesture shows a live transform, then commits a real layout at the new zoom
 * level and a matching scroll position, so panning and momentum stay native
 * and the content is rasterized sharply at rest.
 */
export function useZoomScroller(options: ZoomScrollerOptions) {
  const { scroller, content } = options
  const maxScale = () => Math.max(1, options.maxScale?.() ?? 5)
  const zoomStep = options.zoomStep ?? 0.25
  const scale = ref(1)
  const isGesturing = ref(false)
  const isDragging = ref(false)
  const isZoomed = computed(() => scale.value > 1.001)
  const zoomPercent = computed(() => Math.round(scale.value * 100))

  let session: Session | null = null
  let stopAnimation: (() => void) | null = null
  let animationEnd: { k: number; tx: number; ty: number } | null = null
  let renderFrame: number | null = null
  let wheelTimer: number | undefined
  let blockTarget: HTMLElement | null = null

  const setOverflow = (element: HTMLElement, frozen: boolean) => {
    // At 1x the template's own overflow applies; a zoomed layout pans on both axes.
    const value = frozen ? 'hidden' : scale.value > 1.001 ? 'auto' : ''
    element.style.overflowX = value
    element.style.overflowY = value
  }
  const setActive = (active: boolean) => {
    if (isGesturing.value === active) return
    isGesturing.value = active
    options.onSessionChange?.(active)
  }
  const paint = () => {
    if (session && content.value) content.value.style.transform = `translate(${session.tx}px, ${session.ty}px) scale(${session.k})`
  }
  const scheduleRender = () => {
    if (renderFrame === null) renderFrame = requestAnimationFrame(() => { renderFrame = null; paint() })
  }
  const cancelAnimation = () => { stopAnimation?.(); stopAnimation = null; animationEnd = null }

  const begin = (frozen: boolean) => {
    const element = scroller.value, target = content.value
    if (!element || !target) return null
    if (session) {
      if (frozen && !session.frozen) { session.frozen = true; setOverflow(element, true) }
      return session
    }
    const box = element.getBoundingClientRect(), contentBox = target.getBoundingClientRect()
    const originX = box.left + element.clientLeft, originY = box.top + element.clientTop
    const left = element.scrollLeft, top = element.scrollTop
    session = {
      s0: scale.value, frozen,
      viewWidth: element.clientWidth, viewHeight: element.clientHeight,
      contentWidth: target.offsetWidth, contentHeight: target.offsetHeight,
      offsetX: contentBox.left - originX + left, offsetY: contentBox.top - originY + top,
      left, top, originX, originY, k: 1, tx: 0, ty: 0,
    }
    if (frozen) setOverflow(element, true)
    target.style.transformOrigin = '0 0'
    target.style.willChange = 'transform'
    setActive(true)
    return session
  }

  /** Transform that shows `desired` around a focal point with the committed scroll inside its bounds. */
  const boundedTarget = (state: Session, desired: number, focalX: number, focalY: number) => {
    const k = clamp(desired, 1, maxScale()) / state.s0
    const axis = (focal: number, offset: number, scroll: number, translate: number, size: number, view: number) => {
      const anchor = offset - scroll
      // Keep the content point under the focal point where it is while rescaling.
      const point = (focal - anchor - translate) / state.k
      const free = focal - anchor - k * point
      const scaled = size * k
      const end = options.centered ? Math.max(0, (view - scaled) / 2) : offset
      const committed = clamp(end - offset + scroll - free, 0, Math.max(0, end + scaled - view))
      return end - offset + scroll - committed
    }
    return {
      k,
      tx: axis(focalX, state.offsetX, state.left, state.tx, state.contentWidth, state.viewWidth),
      ty: axis(focalY, state.offsetY, state.top, state.ty, state.contentHeight, state.viewHeight),
    }
  }

  const commit = () => {
    const state = session
    cancelAnimation()
    session = null
    pinch = null
    stopBlockingMoves()
    window.clearTimeout(wheelTimer)
    const element = scroller.value, target = content.value
    if (!state || !element || !target) { setActive(false); return }
    const next = clamp(state.s0 * state.k, 1, maxScale())
    const left = element.scrollLeft, top = element.scrollTop
    options.applyScale(target, next)
    scale.value = next
    target.style.transform = ''
    target.style.transformOrigin = ''
    target.style.willChange = ''
    setOverflow(element, false)
    // One layout read: where the content sits at the new zoom level.
    const box = element.getBoundingClientRect(), contentBox = target.getBoundingClientRect()
    const offsetX = contentBox.left - box.left - element.clientLeft + element.scrollLeft
    const offsetY = contentBox.top - box.top - element.clientTop + element.scrollTop
    // The layout is the transformed one scaled about the content origin, so this keeps every point in place.
    // Unchanged positions are not rewritten: a scroll event would read as the finger scrolling.
    const nextLeft = left + offsetX - state.offsetX - state.tx
    const nextTop = top + offsetY - state.offsetY - state.ty
    if (Math.abs(element.scrollLeft - nextLeft) > 0.5) element.scrollLeft = nextLeft
    if (Math.abs(element.scrollTop - nextTop) > 0.5) element.scrollTop = nextTop
    setActive(false)
  }

  const animateTo = (end: { k: number; tx: number; ty: number }) => {
    const state = session
    if (!state) return
    cancelAnimation()
    animationEnd = end
    const springs: Record<'k' | 'tx' | 'ty', SpringValue> = {
      k: { value: state.k, velocity: 0, target: end.k },
      tx: { value: state.tx, velocity: 0, target: end.tx },
      ty: { value: state.ty, velocity: 0, target: end.ty },
    }
    stopAnimation = animateFrames(elapsed => {
      for (const spring of Object.values(springs)) stepSpring(spring, elapsed, SPRING_OMEGA)
      const done = springAtRest(springs.k, 0.0005) && springAtRest(springs.tx, 0.3) && springAtRest(springs.ty, 0.3)
      state.k = done ? end.k : springs.k.value
      state.tx = done ? end.tx : springs.tx.value
      state.ty = done ? end.ty : springs.ty.value
      paint()
      if (done) { stopAnimation = null; animationEnd = null; commit() }
      return !done
    })
  }

  const settle = (focalX: number, focalY: number) => {
    const state = session
    if (!state) return
    animateTo(boundedTarget(state, state.s0 * state.k, focalX, focalY))
  }
  /** Ends a session at once: where its animation was heading, or its current zoom level within bounds. */
  const finishNow = () => {
    if (!session) return
    const end = animationEnd ?? boundedTarget(session, session.s0 * session.k, lastMidX, lastMidY)
    cancelAnimation()
    Object.assign(session, end)
    commit()
  }

  /** Zooms to `desired` around a client point (the viewport centre by default). */
  const zoomTo = (desired: number, clientX?: number, clientY?: number, animated = true, frozen = false) => {
    if (!scroller.value || !content.value) { scale.value = clamp(desired, 1, maxScale()); return }
    const state = begin(frozen)
    if (!state) return
    window.clearTimeout(wheelTimer)
    const focalX = clientX === undefined ? state.viewWidth / 2 : clientX - state.originX
    const focalY = clientY === undefined ? state.viewHeight / 2 : clientY - state.originY
    const end = boundedTarget(state, desired, focalX, focalY)
    if (animated) { animateTo(end); return }
    Object.assign(state, end)
    commit()
  }
  const zoomIn = (step = zoomStep) => zoomTo(scale.value + step)
  const zoomOut = (step = zoomStep) => zoomTo(scale.value - step)
  const reset = (animated = false) => {
    if (!session && !isZoomed.value) return
    zoomTo(1, undefined, undefined, animated)
  }

  // Trackpad pinches arrive as a stream of ctrl+wheel events; follow them directly and commit once they stop.
  const handleWheelZoom = (event: WheelEvent) => {
    event.preventDefault()
    const state = begin(false)
    if (!state) return
    cancelAnimation()
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? state.viewHeight : 1
    const next = clamp(state.s0 * state.k * Math.exp(-event.deltaY * unit * 0.002), 1, maxScale())
    const k = next / state.s0
    const focalX = Number.isFinite(event.clientX) ? event.clientX - state.originX : state.viewWidth / 2
    const focalY = Number.isFinite(event.clientY) ? event.clientY - state.originY : state.viewHeight / 2
    state.tx = focalX - (state.offsetX - state.left) - k * (focalX - (state.offsetX - state.left) - state.tx) / state.k
    state.ty = focalY - (state.offsetY - state.top) - k * (focalY - (state.offsetY - state.top) - state.ty) / state.k
    state.k = k
    scheduleRender()
    window.clearTimeout(wheelTimer)
    wheelTimer = window.setTimeout(() => settle(focalX, focalY), WHEEL_SETTLE_MS)
  }

  // Past the limits a pinch meets growing resistance instead of a hard stop.
  const resist = (raw: number) => {
    const high = maxScale()
    if (raw > high) return high * Math.pow(raw / high, 0.3)
    if (raw < 1) return Math.pow(raw, 0.45)
    return raw
  }

  let pinch: { distance: number; x: number; y: number; k: number; tx: number; ty: number } | null = null
  let lastMidX = 0, lastMidY = 0
  let tap: { x: number; y: number; time: number; moved: boolean } | null = null
  let lastTap: { x: number; y: number; time: number } | null = null
  let suppressClick = false
  let doubleTapAt = 0

  // Installed only while two fingers are down, so ordinary scrolling never waits for script.
  const blockMove = (event: TouchEvent) => { if (pinch && event.cancelable) event.preventDefault() }
  function stopBlockingMoves() {
    blockTarget?.removeEventListener('touchmove', blockMove)
    blockTarget = null
  }
  const midpoint = (touches: TouchList, state: Session) => ({
    x: (touches[0]!.clientX + touches[1]!.clientX) / 2 - state.originX,
    y: (touches[0]!.clientY + touches[1]!.clientY) / 2 - state.originY,
    distance: Math.max(1, Math.hypot(touches[0]!.clientX - touches[1]!.clientX, touches[0]!.clientY - touches[1]!.clientY)),
  })
  const startPinch = (touches: TouchList) => {
    const state = begin(true)
    if (!state) return
    cancelAnimation()
    window.clearTimeout(wheelTimer)
    const point = midpoint(touches, state)
    pinch = { distance: point.distance, x: point.x, y: point.y, k: state.k, tx: state.tx, ty: state.ty }
    lastMidX = point.x; lastMidY = point.y
    if (!blockTarget && scroller.value) {
      blockTarget = scroller.value
      blockTarget.addEventListener('touchmove', blockMove, { passive: false })
    }
  }

  const onTouchStart = (event: TouchEvent) => {
    if (event.touches.length >= 2) {
      const pinching = !!pinch
      tap = null; lastTap = null; suppressClick = true
      startPinch(event.touches)
      if (!pinching) options.onPinchStart?.()
      return
    }
    // A settling zoom finishes at once, so this finger can scroll natively.
    if (!pinch) finishNow()
    // Browsers send no click after a pinch, so a new touch starts with nothing to suppress.
    if (!pinch && event.touches.length === 1) suppressClick = false
    const touch = event.touches[0]
    tap = touch ? { x: touch.clientX, y: touch.clientY, time: performance.now(), moved: false } : null
  }
  const onTouchMove = (event: TouchEvent) => {
    const state = session
    if (pinch && state && event.touches.length >= 2) {
      const point = midpoint(event.touches, state)
      const k = resist(state.s0 * pinch.k * point.distance / pinch.distance) / state.s0
      // The content point that started under the fingers' midpoint follows it.
      const anchorX = state.offsetX - state.left, anchorY = state.offsetY - state.top
      state.tx = point.x - anchorX - k * (pinch.x - anchorX - pinch.tx) / pinch.k
      state.ty = point.y - anchorY - k * (pinch.y - anchorY - pinch.ty) / pinch.k
      state.k = k
      lastMidX = point.x; lastMidY = point.y
      scheduleRender()
      return
    }
    const touch = event.touches[0]
    if (tap && touch && Math.hypot(touch.clientX - tap.x, touch.clientY - tap.y) > TAP_SLOP) tap.moved = true
  }
  const onTouchEnd = (event: TouchEvent) => {
    if (pinch) {
      if (event.type !== 'touchcancel' && event.touches.length >= 2) { startPinch(event.touches); return }
      pinch = null
      stopBlockingMoves()
      settle(lastMidX, lastMidY)
      tap = null
      return
    }
    const start = tap
    tap = null
    const touch = event.changedTouches[0]
    if (event.type === 'touchcancel' || event.touches.length || !start || !touch) return
    if (!start.moved && performance.now() - start.time < TAP_MS) { handleTap(touch.clientX, touch.clientY); return }
    const dx = touch.clientX - start.x, dy = touch.clientY - start.y
    if (options.onSwipe && !isZoomed.value && Math.abs(dx) >= 60 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      suppressClick = true
      options.onSwipe(dx < 0 ? 1 : -1)
    }
  }
  const handleTap = (x: number, y: number) => {
    const now = performance.now()
    if (options.doubleTapScale && lastTap && now - lastTap.time < DOUBLE_TAP_MS && Math.hypot(x - lastTap.x, y - lastTap.y) < DOUBLE_TAP_SLOP) {
      lastTap = null
      doubleTapAt = now
      suppressClick = true
      zoomTo(isZoomed.value ? 1 : options.doubleTapScale(), x, y, true, true)
      options.onDoubleTap?.()
      return
    }
    lastTap = { x, y, time: now }
  }
  /** Safari's own page pinch would otherwise compete with ours. */
  const onGesture = (event: Event) => event.preventDefault()

  let drag: { x: number; y: number; left: number; top: number } | null = null
  const onMouseMove = (event: MouseEvent) => {
    const element = scroller.value
    if (!drag || !element) return
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y
    if (!isDragging.value && Math.hypot(dx, dy) > 4) isDragging.value = true
    element.scrollLeft = drag.left - dx
    element.scrollTop = drag.top - dy
  }
  const onMouseUp = () => {
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
    if (isDragging.value) suppressClick = true
    isDragging.value = false
    drag = null
  }
  /** Mouse dragging pans a zoomed layout; touch, wheel and trackpad scrolling are already native. */
  const onMouseDown = (event: MouseEvent) => {
    if (event.button !== 0) return
    // Grabbing a zoom that is still animating finishes it, then drags.
    if (!pinch) finishNow()
    const element = scroller.value
    if (!isZoomed.value || session || !element) return
    event.preventDefault()
    drag = { x: event.clientX, y: event.clientY, left: element.scrollLeft, top: element.scrollTop }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }

  /** True once for the click that ends a pinch, double-tap, swipe or drag. */
  const wasGesture = () => {
    const suppressed = suppressClick
    suppressClick = false
    return suppressed
  }
  /** True once for the dblclick a browser synthesizes after a handled double-tap. */
  const wasDoubleTap = () => {
    const handled = doubleTapAt > 0 && performance.now() - doubleTapAt < 500
    doubleTapAt = 0
    return handled
  }

  const onKeydown = (event: KeyboardEvent) => {
    if (options.keyboard && !options.keyboard()) return
    const target = event.target as HTMLElement | null
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
    if (event.key === '+' || event.key === '=') { event.preventDefault(); zoomIn() }
    else if (event.key === '-' || event.key === '_') { event.preventDefault(); zoomOut() }
    else if (event.key === '0') { event.preventDefault(); reset(true) }
  }

  // A newly mounted surface takes the current zoom level; an interrupted session is dropped.
  watch([scroller, content], ([element, target], [previousElement, previousTarget]) => {
    if (session && (element !== previousElement || target !== previousTarget)) {
      cancelAnimation()
      stopBlockingMoves()
      session = null
      pinch = null
      if (previousTarget) { previousTarget.style.transform = ''; previousTarget.style.willChange = '' }
      setActive(false)
    }
    if (target) options.applyScale(target, scale.value)
    if (element) setOverflow(element, false)
  }, { flush: 'post', immediate: true })

  onMounted(() => window.addEventListener('keydown', onKeydown))
  onBeforeUnmount(() => {
    cancelAnimation()
    stopBlockingMoves()
    if (renderFrame !== null) cancelAnimationFrame(renderFrame)
    window.clearTimeout(wheelTimer)
    window.removeEventListener('keydown', onKeydown)
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  })

  return {
    scale, isZoomed, zoomPercent, isGesturing, isDragging,
    zoomTo, zoomIn, zoomOut, reset, handleWheelZoom,
    onTouchStart, onTouchMove, onTouchEnd, onGesture, onMouseDown,
    wasGesture, wasDoubleTap,
  }
}
