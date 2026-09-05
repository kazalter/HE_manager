import { computed, onMounted, onUnmounted, ref, type ComputedRef } from 'vue'

/** Fullscreen and auto-hide control lifecycle shared by media viewers. */
export function useMediaOverlayControls(
  isManga: ComputedRef<boolean>,
  isImage: ComputedRef<boolean>,
) {
  const isFullscreen = ref(false)
  const showControls = ref(true)
  const isHoveringControls = ref(false)
  const clickOnlyControls = computed(() => isFullscreen.value && (isManga.value || isImage.value))
  let controlTimer: number | undefined
  let viewerClickTimer: number | undefined

  const clearTimer = () => {
    window.clearTimeout(controlTimer)
    controlTimer = undefined
  }

  const startAutoHideTimer = (delay = 3500) => {
    clearTimer()
    if (isHoveringControls.value) return
    controlTimer = window.setTimeout(() => {
      if (!isHoveringControls.value) {
        showControls.value = false
      }
    }, delay)
  }

  const resetTimer = () => {
    if (clickOnlyControls.value) return
    showControls.value = true
    if (!isHoveringControls.value) {
      startAutoHideTimer(2500)
    }
  }

  const setControlsHover = (hovering: boolean) => {
    isHoveringControls.value = hovering
    if (hovering) {
      clearTimer()
      showControls.value = true
    } else if (showControls.value) {
      startAutoHideTimer(3000)
    }
  }

  const toggleViewerControls = () => {
    if (!clickOnlyControls.value) {
      resetTimer()
      return
    }
    clearTimer()
    if (showControls.value) {
      showControls.value = false
      isHoveringControls.value = false
      return
    }
    showControls.value = true
    startAutoHideTimer(4000)
  }

  const handleViewerClick = () => {
    window.clearTimeout(viewerClickTimer)
    viewerClickTimer = window.setTimeout(() => {
      viewerClickTimer = undefined
      toggleViewerControls()
    }, 240)
  }

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) void document.documentElement.requestFullscreen()
    else void document.exitFullscreen()
  }

  const handleViewerDoubleClick = () => {
    window.clearTimeout(viewerClickTimer)
    viewerClickTimer = undefined
    toggleFullscreen()
  }

  const onFullscreenChange = () => {
    isFullscreen.value = !!document.fullscreenElement
    clearTimer()
    showControls.value = true
    if (clickOnlyControls.value) {
      startAutoHideTimer(4000)
    }
  }

  const onMouseMove = () => {
    if (clickOnlyControls.value) {
      // In fullscreen mode: moving mouse while controls are open keeps them visible
      if (showControls.value && !isHoveringControls.value) {
        startAutoHideTimer(3500)
      }
      return
    }
    resetTimer()
  }

  onMounted(() => {
    document.body.style.overflow = 'hidden'
    window.addEventListener('mousemove', onMouseMove)
    document.addEventListener('fullscreenchange', onFullscreenChange)
    resetTimer()
  })

  onUnmounted(() => {
    document.body.style.overflow = 'auto'
    window.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('fullscreenchange', onFullscreenChange)
    clearTimer()
    window.clearTimeout(viewerClickTimer)
    if (document.fullscreenElement) void document.exitFullscreen()
  })

  return {
    isFullscreen,
    showControls,
    clickOnlyControls,
    isHoveringControls,
    setControlsHover,
    resetTimer,
    handleViewerClick,
    handleViewerDoubleClick,
    toggleFullscreen,
  }
}
