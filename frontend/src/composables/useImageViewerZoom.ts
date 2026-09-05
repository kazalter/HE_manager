import { computed, onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

export interface UseImageViewerZoomOptions {
  minScale?: number
  maxScale?: number
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

  const isZoomed = computed(() => scale.value > 1.01)
  const zoomPercent = computed(() => Math.round(scale.value * 100))

  const clampTranslation = (tx: number, ty: number, currentScale: number, rect?: DOMRect) => {
    const container = containerRef.value
    const r = rect || container?.getBoundingClientRect()
    if (!r || currentScale <= 1.01) {
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
    const targetScale = Math.min(maxScale, Math.max(minScale, Number(newScale.toFixed(2))))
    if (targetScale <= 1.01) {
      scale.value = 1
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
  }

  const handleZoomWheel = (event: WheelEvent) => {
    event.preventDefault()
    // deltaY < 0 means scroll up (zoom in), deltaY > 0 means scroll down (zoom out)
    const factor = event.deltaY < 0 ? 1.15 : 0.87
    setScale(scale.value * factor, event.clientX, event.clientY)
  }

  const onMouseDown = (event: MouseEvent) => {
    dragDistance = 0
    hasDragged = false
    if (scale.value <= 1.01 || event.button !== 0) return
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
    if (scale.value <= 1.01) {
      hasDragged = false
      dragDistance = 0
      return false
    }
    const dragged = hasDragged
    hasDragged = false
    dragDistance = 0
    return dragged
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
    wasDragging,
  }
}
