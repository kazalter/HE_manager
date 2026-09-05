import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { computed, defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { useMediaOverlayControls } from '../composables/useMediaOverlayControls'

describe('useMediaOverlayControls composable', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  const createControls = (isMangaVal = true) => {
    let controls!: ReturnType<typeof useMediaOverlayControls>
    const Comp = defineComponent({
      setup() {
        controls = useMediaOverlayControls(computed(() => isMangaVal), computed(() => false))
        return () => null
      },
    })
    const wrapper = mount(Comp)
    return { wrapper, controls }
  }

  it('keeps controls open indefinitely while user hovers over controls in fullscreen', () => {
    const { wrapper, controls } = createControls(true)

    // Simulate entering fullscreen
    controls.isFullscreen.value = true
    expect(controls.clickOnlyControls.value).toBe(true)

    // Fullscreen starts with controls hidden
    controls.showControls.value = false

    // Click viewer to open controls
    controls.handleViewerClick()
    vi.advanceTimersByTime(240) // debounce for viewerClick
    expect(controls.showControls.value).toBe(true)

    // User hovers over thumbnail strip / controls
    controls.setControlsHover(true)
    expect(controls.isHoveringControls.value).toBe(true)

    // Advance timers by 10 seconds (well past the old 1.8s timeout)
    vi.advanceTimersByTime(10000)
    expect(controls.showControls.value).toBe(true)

    // User leaves controls
    controls.setControlsHover(false)
    expect(controls.isHoveringControls.value).toBe(false)

    // After leaving, controls stay open for 3 seconds, then hide
    vi.advanceTimersByTime(2900)
    expect(controls.showControls.value).toBe(true)

    vi.advanceTimersByTime(200)
    expect(controls.showControls.value).toBe(false)

    wrapper.unmount()
  })

  it('resets auto-hide timer when mouse moves while controls are already open in fullscreen', () => {
    const { wrapper, controls } = createControls(true)

    controls.isFullscreen.value = true
    controls.showControls.value = false

    // Click viewer to open controls
    controls.handleViewerClick()
    vi.advanceTimersByTime(240)
    expect(controls.showControls.value).toBe(true)

    // Advance 3 seconds (out of 4s initial timer)
    vi.advanceTimersByTime(3000)
    expect(controls.showControls.value).toBe(true)

    // User moves mouse across screen
    window.dispatchEvent(new MouseEvent('mousemove'))

    // Advance 3 more seconds (would have expired without mousemove)
    vi.advanceTimersByTime(3000)
    expect(controls.showControls.value).toBe(true)

    // Wait for idle timeout (3500ms total after mousemove)
    vi.advanceTimersByTime(600)
    expect(controls.showControls.value).toBe(false)

    wrapper.unmount()
  })

  it('does not open controls on mousemove when controls are closed in fullscreen', () => {
    const { wrapper, controls } = createControls(true)

    controls.isFullscreen.value = true
    controls.showControls.value = false

    // Move mouse
    window.dispatchEvent(new MouseEvent('mousemove'))
    expect(controls.showControls.value).toBe(false)

    wrapper.unmount()
  })
})
