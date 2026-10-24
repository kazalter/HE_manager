import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'

export interface UseImageViewerZoomOptions {
  minScale?: number
  maxScale?: number
  onSwipe?: (direction: -1 | 1) => void
  zoomStep?: number
  /**
   * Element that receives the transform. When given, the composable writes its
   * style directly, so a gesture never re-renders the component that owns it.
   */
  contentRef?: Ref<HTMLElement | null>
  /** Unscaled size of the visible image inside the container; panning stops at its edges. */
  contentSize?: (width: number, height: number) => { width: number; height: number } | null
  /** A touch double-tap toggles between fit and this scale around the tapped point. */
  doubleTapScale?: number
  onDoubleTap?: () => void
}

const SETTLE_TRANSITION = 'transform 0.22s cubic-bezier(0.2, 0.8, 0.2, 1)'
// Past a limit, only this power of the finger ratio is applied (rubber band).
const OVERSCALE_RESISTANCE = 0.3
const OVERSCALE_LIMIT = 0.25
// Per-millisecond velocity retention for a released pan.
const FLING_DECAY = 0.996
const FLING_MIN_SPEED = 0.12
const DOUBLE_TAP_MS = 300
const DOUBLE_TAP_SLOP = 30

export function useImageViewerZoom(
  containerRef: Ref<HTMLElement | null>,
  options: UseImageViewerZoomOptions = {},
) {
  const minScale = options.minScale ?? 1
  const maxScale = options.maxScale ?? 5
  const zoomStep = options.zoomStep ?? 0.25

  const scale = ref(1)
  const translateX = ref(0)
  const translateY = ref(0)
  const isPanning = ref(false)
  // Display-only scale, updated when a continuous gesture settles rather than per frame.
  const settledScale = ref(1)

  let isMouseDown = false
  let startX = 0
  let startY = 0
  let startTx = 0
  let startTy = 0
  let dragDistance = 0
  let hasDragged = false
  let animateNext = false
  let wheeling = false
  let wheelTimer: number | undefined

  const isZoomed = computed(() => scale.value > 1.0001)
  const zoomPercent = computed(() => Math.round(settledScale.value * 100))

  const render = () => {
    const element = options.contentRef?.value
    if (!element) return
    const live = isPanning.value || wheeling
    element.style.transform = `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`
    element.style.transition = animateNext && !live ? SETTLE_TRANSITION : 'none'
    // A 2D transform plus will-change composites only while the image moves;
    // at rest it is painted at the final scale instead of a stretched bitmap.
    element.style.willChange = live ? 'transform' : ''
    animateNext = false
  }
  if (options.contentRef) watch(options.contentRef, render, { flush: 'post' })

  const panBounds = (currentScale: number, r: DOMRect) => {
    const size = options.contentSize?.(r.width, r.height)
    const width = size?.width || r.width
    const height = size?.height || r.height
    return {
      x: Math.max(0, (currentScale * width - r.width) / 2),
      y: Math.max(0, (currentScale * height - r.height) / 2),
    }
  }

  const clampTranslation = (tx: number, ty: number, currentScale: number, rect?: DOMRect) => {
    const container = containerRef.value
    const r = rect || container?.getBoundingClientRect()
    if (!r || currentScale <= 1) {
      translateX.value = 0
      translateY.value = 0
      return
    }
    const bounds = panBounds(currentScale, r)
    translateX.value = Math.max(-bounds.x, Math.min(bounds.x, tx))
    translateY.value = Math.max(-bounds.y, Math.min(bounds.y, ty))
  }

  let flingRaf: number | null = null
  const stopFling = () => {
    if (flingRaf !== null) cancelAnimationFrame(flingRaf)
    flingRaf = null
  }
  const settle = () => {
    stopFling()
    isPanning.value = false
    settledScale.value = scale.value
    render()
  }

  const zoomAt = (newScale: number, centerClientX?: number, centerClientY?: number, rect?: DOMRect) => {
    const targetScale = Math.min(maxScale, Math.max(minScale, newScale))
    if (targetScale <= 1) {
      scale.value = targetScale
      translateX.value = 0
      translateY.value = 0
      hasDragged = false
      dragDistance = 0
      return
    }

    const container = containerRef.value
    const r = rect || container?.getBoundingClientRect()
    if (r && centerClientX !== undefined && centerClientY !== undefined && scale.value > 0) {
      const mouseX = centerClientX - (r.left + r.width / 2)
      const mouseY = centerClientY - (r.top + r.height / 2)
      const scaleRatio = targetScale / scale.value
      const newTx = mouseX - (mouseX - translateX.value) * scaleRatio
      const newTy = mouseY - (mouseY - translateY.value) * scaleRatio
      scale.value = targetScale
      clampTranslation(newTx, newTy, targetScale, r)
    } else {
      scale.value = targetScale
      clampTranslation(translateX.value, translateY.value, targetScale, r)
    }
  }

  const setScale = (newScale: number, centerClientX?: number, centerClientY?: number) => {
    stopFling()
    // Programmatic zooms end an active pan or fling, so settle styles can animate and release.
    isPanning.value = false
    zoomAt(newScale, centerClientX, centerClientY)
    settledScale.value = scale.value
    render()
  }

  const animateTo = (newScale: number, centerClientX?: number, centerClientY?: number) => {
    animateNext = true
    setScale(newScale, centerClientX, centerClientY)
  }

  const zoomIn = (step = zoomStep) => {
    animateTo(scale.value + step)
  }

  const zoomOut = (step = zoomStep) => {
    animateTo(scale.value - step)
  }

  const resetZoom = (animated = false) => {
    stopFling()
    window.clearTimeout(wheelTimer)
    wheeling = false
    scale.value = 1
    settledScale.value = 1
    translateX.value = 0
    translateY.value = 0
    isPanning.value = false
    isMouseDown = false
    hasDragged = false
    dragDistance = 0
    multipleTouches = false
    hadMultipleTouches = false
    suppressTouchClick = false
    pinchDistance = 0
    animateNext = animated === true
    render()
  }

  const handleZoomWheel = (event: WheelEvent) => {
    event.preventDefault()
    stopFling()
    // deltaY < 0 means scroll up (zoom in), deltaY > 0 means scroll down (zoom out)
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? (containerRef.value?.clientHeight || 800) : 1
    const factor = Math.exp(-event.deltaY * unit * 0.002)
    // Trackpad pinches arrive as a stream of wheel events; follow them without easing.
    wheeling = true
    window.clearTimeout(wheelTimer)
    wheelTimer = window.setTimeout(() => { wheeling = false; settle() }, 150)
    zoomAt(scale.value * factor, event.clientX, event.clientY)
    render()
  }

  // Recent translations, used for the release velocity of a pan.
  let samples: Array<[number, number, number]> = []
  const resetSamples = () => { samples = [] }
  const trackSample = () => {
    const now = performance.now()
    samples.push([now, translateX.value, translateY.value])
    while (samples.length > 2 && now - samples[0]![0] > 100) samples.shift()
  }
  const fling = (rect?: DOMRect) => {
    const first = samples[0], last = samples.at(-1)
    resetSamples()
    const elapsed = first && last ? last[0] - first[0] : 0
    // A finger that paused before lifting should not throw the image.
    if (!first || !last || elapsed < 8 || performance.now() - last[0] > 60 || !isZoomed.value) return settle()
    let vx = (last[1] - first[1]) / elapsed
    let vy = (last[2] - first[2]) / elapsed
    if (Math.hypot(vx, vy) < FLING_MIN_SPEED) return settle()
    const r = rect || containerRef.value?.getBoundingClientRect()
    isPanning.value = true
    let previous = performance.now()
    const step = (now: number) => {
      const elapsedFrame = Math.min(32, Math.max(0, now - previous))
      previous = now
      const decay = Math.pow(FLING_DECAY, elapsedFrame)
      vx *= decay; vy *= decay
      const nextX = translateX.value + vx * elapsedFrame
      const nextY = translateY.value + vy * elapsedFrame
      clampTranslation(nextX, nextY, scale.value, r)
      // Stop each axis at the image edge instead of sliding along it forever.
      if (translateX.value !== nextX) vx = 0
      if (translateY.value !== nextY) vy = 0
      render()
      if (Math.hypot(vx, vy) < 0.02) { flingRaf = null; settle(); return }
      flingRaf = requestAnimationFrame(step)
    }
    flingRaf = requestAnimationFrame(step)
  }

  const onMouseDown = (event: MouseEvent) => {
    dragDistance = 0
    hasDragged = false
    stopFling()
    if (scale.value <= 1 || event.button !== 0) return
    isMouseDown = true
    isPanning.value = true
    startX = event.clientX
    startY = event.clientY
    startTx = translateX.value
    startTy = translateY.value
    resetSamples()
    render()

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }

  const onMouseMove = (event: MouseEvent) => {
    if (!isMouseDown) return
    const dx = event.clientX - startX
    const dy = event.clientY - startY
    dragDistance = Math.hypot(dx, dy)
    if (dragDistance > 8) {
      hasDragged = true
    }
    clampTranslation(startTx + dx, startTy + dy, scale.value)
    trackSample()
    render()
  }

  const onMouseUp = () => {
    isMouseDown = false
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
    fling()
  }

  const wasDragging = () => {
    if (scale.value <= 1) {
      hasDragged = false
      dragDistance = 0
      return false
    }
    const dragged = hasDragged
    hasDragged = false
    dragDistance = 0
    return dragged
  }

  // Applies a finger ratio, resisting (not stopping) beyond the scale limits so
  // reversing direction still responds on the very next sample.
  const resistScale = (current: number, ratio: number) => {
    const next = current * ratio
    const bound = ratio < 1 ? minScale : maxScale
    if (ratio < 1 ? next >= bound : next <= bound) return next
    const from = (ratio < 1 ? current < bound : current > bound) ? current : bound
    const resisted = from * Math.pow(next / from, OVERSCALE_RESISTANCE)
    return Math.min(maxScale * (1 + OVERSCALE_LIMIT), Math.max(minScale * (1 - OVERSCALE_LIMIT), resisted))
  }

  let pinchDistance = 0
  let pinchX = 0, pinchY = 0
  let touchRect: DOMRect | undefined
  let touchX = 0, touchY = 0, touchTx = 0, touchTy = 0
  let multipleTouches = false
  let hadMultipleTouches = false
  let suppressTouchClick = false
  let lastTapAt = 0, lastTapX = 0, lastTapY = 0, doubleTapAt = 0
  const distance = (touches: TouchList) => Math.hypot(touches[0]!.clientX - touches[1]!.clientX, touches[0]!.clientY - touches[1]!.clientY)
  const startTouchPan = (touch: Touch) => {
    touchX = touch.clientX; touchY = touch.clientY
    touchTx = translateX.value; touchTy = translateY.value
    resetSamples()
  }
  const onTouchStart = (event: TouchEvent) => {
    if (!event.touches.length) return
    stopFling()
    if (event.touches.length === 1) {
      startTouchPan(event.touches[0]!)
      multipleTouches = false; hadMultipleTouches = false; suppressTouchClick = false
      touchRect = containerRef.value?.getBoundingClientRect()
      isPanning.value = isZoomed.value
    } else {
      multipleTouches = true; hadMultipleTouches = true; suppressTouchClick = true
      pinchDistance = distance(event.touches)
      pinchX = (event.touches[0]!.clientX + event.touches[1]!.clientX) / 2
      pinchY = (event.touches[0]!.clientY + event.touches[1]!.clientY) / 2
      touchRect = containerRef.value?.getBoundingClientRect()
      isPanning.value = true
      if (event.cancelable) event.preventDefault()
    }
    render()
  }
  const onTouchMove = (event: TouchEvent) => {
    if (event.touches.length >= 2 && pinchDistance > 0) {
      if (event.cancelable) event.preventDefault()
      const x = (event.touches[0]!.clientX + event.touches[1]!.clientX) / 2
      const y = (event.touches[0]!.clientY + event.touches[1]!.clientY) / 2
      const nextDistance = distance(event.touches)
      const targetScale = resistScale(scale.value, nextDistance / pinchDistance)
      const ratio = targetScale / scale.value
      const cx = touchRect ? touchRect.left + touchRect.width / 2 : x
      const cy = touchRect ? touchRect.top + touchRect.height / 2 : y
      const tx = x - cx - (pinchX - cx - translateX.value) * ratio
      const ty = y - cy - (pinchY - cy - translateY.value) * ratio
      scale.value = targetScale
      clampTranslation(tx, ty, targetScale, touchRect)
      // Rebase every sample, including at the limits, so reversing the fingers
      // responds immediately rather than working through accumulated overshoot.
      pinchDistance = Math.max(1, nextDistance); pinchX = x; pinchY = y
      render()
    } else if (event.touches.length === 1 && !multipleTouches) {
      const dx = event.touches[0]!.clientX - touchX, dy = event.touches[0]!.clientY - touchY
      if (Math.hypot(dx, dy) > 8) suppressTouchClick = true
      if (isZoomed.value) {
        if (event.cancelable) event.preventDefault()
        clampTranslation(touchTx + dx, touchTy + dy, scale.value, touchRect)
        trackSample()
        render()
      }
    }
  }
  // Springs back from a rubber-banded pinch around the last pinch centre.
  const settleScaleOvershoot = () => {
    if (scale.value >= minScale && scale.value <= maxScale) return false
    stopFling()
    isPanning.value = false
    animateNext = true
    zoomAt(scale.value, pinchX, pinchY, touchRect)
    settledScale.value = scale.value
    render()
    return true
  }
  const handleTap = (touch: Touch) => {
    if (!options.doubleTapScale) return false
    const now = performance.now()
    if (now - lastTapAt < DOUBLE_TAP_MS && Math.hypot(touch.clientX - lastTapX, touch.clientY - lastTapY) < DOUBLE_TAP_SLOP) {
      lastTapAt = 0
      doubleTapAt = now
      suppressTouchClick = true
      if (isZoomed.value) animateTo(1)
      else animateTo(options.doubleTapScale, touch.clientX, touch.clientY)
      options.onDoubleTap?.()
      return true
    }
    lastTapAt = now; lastTapX = touch.clientX; lastTapY = touch.clientY
    return false
  }
  const onTouchEnd = (event: TouchEvent) => {
    if (event.type === 'touchcancel') {
      suppressTouchClick = true; hadMultipleTouches = true
      multipleTouches = false; pinchDistance = 0
      if (!settleScaleOvershoot()) settle()
      return
    }
    if (event.touches.length === 1 && multipleTouches) {
      startTouchPan(event.touches[0]!)
      multipleTouches = false
      isPanning.value = isZoomed.value
      render()
      return
    }
    if (event.touches.length) return
    multipleTouches = false
    pinchDistance = 0
    if (settleScaleOvershoot()) { lastTapAt = 0; return }
    // A pinch remains a multi-touch gesture until every finger is released,
    // even after one finger continues panning or the scale returns to 1x.
    const touch = event.changedTouches[0]
    if (!touch || hadMultipleTouches) { lastTapAt = 0; settle(); return }
    if (!suppressTouchClick && handleTap(touch)) return
    if (isZoomed.value) { fling(touchRect); return }
    settle()
    const dx = touch.clientX - touchX, dy = touch.clientY - touchY
    if (Math.abs(dx) >= 60 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      suppressTouchClick = true
      options.onSwipe?.(dx < 0 ? 1 : -1)
    }
  }
  const wasTouchGesture = () => {
    const suppressed = suppressTouchClick
    suppressTouchClick = false
    return suppressed
  }
  /** True once for the dblclick a browser synthesizes after a handled double-tap. */
  const wasDoubleTap = () => {
    const handled = doubleTapAt > 0 && performance.now() - doubleTapAt < 500
    doubleTapAt = 0
    return handled
  }

  const onKeydown = (event: KeyboardEvent) => {
    const target = event.target as HTMLElement | null
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
      return
    }
    if (event.key === '+' || event.key === '=') {
      event.preventDefault()
      zoomIn()
    } else if (event.key === '-' || event.key === '_') {
      event.preventDefault()
      zoomOut()
    } else if (event.key === '0') {
      event.preventDefault()
      resetZoom(true)
    }
  }

  onMounted(() => {
    window.addEventListener('keydown', onKeydown)
  })

  onBeforeUnmount(() => {
    stopFling()
    window.clearTimeout(wheelTimer)
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
    window.removeEventListener('keydown', onKeydown)
  })

  return {
    scale,
    translateX,
    translateY,
    isZoomed,
    isPanning,
    zoomPercent,
    zoomIn,
    zoomOut,
    resetZoom,
    setScale,
    handleZoomWheel,
    onMouseDown,
    onTouchStart, onTouchMove, onTouchEnd, wasTouchGesture, wasDoubleTap,
    wasDragging,
  }
}
