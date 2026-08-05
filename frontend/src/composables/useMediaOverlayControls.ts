import { computed, onMounted, onUnmounted, ref, type ComputedRef } from 'vue'

/** Fullscreen and auto-hide control lifecycle shared by media viewers. */
export function useMediaOverlayControls(
  isManga: ComputedRef<boolean>,
  isImage: ComputedRef<boolean>,
) {
  const isFullscreen = ref(false)
  const showControls = ref(true)
  const clickOnlyControls = computed(() => isFullscreen.value && (isManga.value || isImage.value))
  let controlTimer: number | undefined
  let viewerClickTimer: number | undefined

  const resetTimer = () => {
    if (clickOnlyControls.value) return
    showControls.value = true
    window.clearTimeout(controlTimer)
    controlTimer = window.setTimeout(() => { showControls.value = false }, 1400)
  }

  const toggleViewerControls = () => {
    if (!clickOnlyControls.value) {
      resetTimer()
      return
    }
    window.clearTimeout(controlTimer)
    if (showControls.value) {
      showControls.value = false
      return
    }
    showControls.value = true
    controlTimer = window.setTimeout(() => { showControls.value = false }, 1800)
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
    window.clearTimeout(controlTimer)
    showControls.value = true
    if (clickOnlyControls.value) {
      controlTimer = window.setTimeout(() => { showControls.value = false }, 1800)
    }
  }

  onMounted(() => {
    document.body.style.overflow = 'hidden'
    window.addEventListener('mousemove', resetTimer)
    document.addEventListener('fullscreenchange', onFullscreenChange)
    resetTimer()
  })

  onUnmounted(() => {
    document.body.style.overflow = 'auto'
    window.removeEventListener('mousemove', resetTimer)
    document.removeEventListener('fullscreenchange', onFullscreenChange)
    window.clearTimeout(controlTimer)
    window.clearTimeout(viewerClickTimer)
    if (document.fullscreenElement) void document.exitFullscreen()
  })

  return {
    isFullscreen,
    showControls,
    clickOnlyControls,
    resetTimer,
    handleViewerClick,
    handleViewerDoubleClick,
    toggleFullscreen,
  }
}
