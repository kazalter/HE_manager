import { computed, onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

export interface UseImageViewerZoomOptions {
  minScale?: number
  maxScale?: number
  onSwipe?: (direction: -1 | 1) => void
  zoomStep?: number
}

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

  let isMouseDown = false
  let startX = 0
  let startY = 0
  let startTx = 0
  let startTy = 0
  let dragDistance = 0
  let hasDragged = false

  const isZoomed = computed(() => scale.value > 1.0001)
  const zoomPercent = computed(() => Math.round(scale.value * 100))

  const clampTranslation = (tx: number, ty: number, currentScale: number, rect?: DOMRect) => {
    const container = containerRef.value
    const r = rect || container?.getBoundingClientRect()
    if (!r || currentScale <= 1) {
      translateX.value = 0
      translateY.value = 0
      return
    }
    const maxTx = Math.max(0, ((currentScale - 1) * r.width) / 2)
    const maxTy = Math.max(0, ((currentScale - 1) * r.height) / 2)
    translateX.value = Math.max(-maxTx, Math.min(maxTx, tx))
    translateY.value = Math.max(-maxTy, Math.min(maxTy, ty))
  }

  const setScale = (newScale: number, centerClientX?: number, centerClientY?: number) => {
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
    const rect = container?.getBoundingClientRect()
    if (rect && centerClientX !== undefined && centerClientY !== undefined && scale.value > 0) {
      const mouseX = centerClientX - (rect.left + rect.width / 2)
      const mouseY = centerClientY - (rect.top + rect.height / 2)
      const scaleRatio = targetScale / scale.value
      const newTx = mouseX - (mouseX - translateX.value) * scaleRatio
      const newTy = mouseY - (mouseY - translateY.value) * scaleRatio
      scale.value = targetScale
      clampTranslation(newTx, newTy, targetScale, rect)
    } else {
      scale.value = targetScale
      clampTranslation(translateX.value, translateY.value, targetScale, rect)
    }
  }

  const zoomIn = (step = zoomStep) => {
    setScale(scale.value + step)
  }

  const zoomOut = (step = zoomStep) => {
    setScale(scale.value - step)
  }

  const resetZoom = () => {
    scale.value = 1
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
  }

  const handleZoomWheel = (event: WheelEvent) => {
    event.preventDefault()
    // deltaY < 0 means scroll up (zoom in), deltaY > 0 means scroll down (zoom out)
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? (containerRef.value?.clientHeight || 800) : 1
    const factor = Math.exp(-event.deltaY * unit * 0.002)
    setScale(scale.value * factor, event.clientX, event.clientY)
  }

  const onMouseDown = (event: MouseEvent) => {
    dragDistance = 0
    hasDragged = false
    if (scale.value <= 1 || event.button !== 0) return
    isMouseDown = true
    isPanning.value = true
    startX = event.clientX
    startY = event.clientY
    startTx = translateX.value
    startTy = translateY.value

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
  }

  const onMouseUp = () => {
    isMouseDown = false
    isPanning.value = false
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
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

  let pinchDistance = 0
  let pinchX = 0, pinchY = 0
  let touchRect: DOMRect | undefined
  let touchX = 0, touchY = 0, touchTx = 0, touchTy = 0
  let multipleTouches = false
  let hadMultipleTouches = false
  let suppressTouchClick = false
  const distance = (touches: TouchList) => Math.hypot(touches[0]!.clientX - touches[1]!.clientX, touches[0]!.clientY - touches[1]!.clientY)
  const onTouchStart = (event: TouchEvent) => {
    if (!event.touches.length) return
    if (event.touches.length === 1) {
      touchX = event.touches[0]!.clientX; touchY = event.touches[0]!.clientY
      touchTx = translateX.value; touchTy = translateY.value
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
  }
  const onTouchMove = (event: TouchEvent) => {
    if (event.touches.length >= 2 && pinchDistance > 0) {
      if (event.cancelable) event.preventDefault()
      const x = (event.touches[0]!.clientX + event.touches[1]!.clientX) / 2
      const y = (event.touches[0]!.clientY + event.touches[1]!.clientY) / 2
      const nextDistance = distance(event.touches)
      const targetScale = Math.min(maxScale, Math.max(minScale, scale.value * nextDistance / pinchDistance))
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
    } else if (event.touches.length === 1 && !multipleTouches) {
      const dx = event.touches[0]!.clientX - touchX, dy = event.touches[0]!.clientY - touchY
      if (Math.hypot(dx, dy) > 8) suppressTouchClick = true
      if (isZoomed.value) {
        if (event.cancelable) event.preventDefault()
        clampTranslation(touchTx + dx, touchTy + dy, scale.value, touchRect)
      }
    }
  }
  const onTouchEnd = (event: TouchEvent) => {
    isPanning.value = false
    if (event.type === 'touchcancel') {
      suppressTouchClick = true; hadMultipleTouches = true
      multipleTouches = false; pinchDistance = 0
      return
    }
    if (event.touches.length === 1 && multipleTouches) {
      touchX = event.touches[0]!.clientX; touchY = event.touches[0]!.clientY
      touchTx = translateX.value; touchTy = translateY.value
      multipleTouches = false
      isPanning.value = isZoomed.value
      return
    }
    if (event.touches.length === 0) {
      multipleTouches = false
      pinchDistance = 0
    }
    // A pinch remains a multi-touch gesture until every finger is released,
    // even after one finger continues panning or the scale returns to 1x.
    if (event.touches.length || hadMultipleTouches || isZoomed.value || !event.changedTouches.length) return
    const dx = event.changedTouches[0]!.clientX - touchX, dy = event.changedTouches[0]!.clientY - touchY
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
      resetZoom()
    }
  }

  onMounted(() => {
    window.addEventListener('keydown', onKeydown)
  })

  onBeforeUnmount(() => {
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
    onTouchStart, onTouchMove, onTouchEnd, wasTouchGesture,
    wasDragging,
  }
}
