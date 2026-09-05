import { describe, it, expect, afterEach } from 'vitest'
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useImageViewerZoom } from '../composables/useImageViewerZoom'

describe('useImageViewerZoom composable', () => {
  const createTestViewer = (options = {}) => {
    let zoom!: ReturnType<typeof useImageViewerZoom>
    const containerRef = ref<HTMLDivElement | null>(null)

    const Comp = defineComponent({
      setup() {
        zoom = useImageViewerZoom(containerRef, options)
        return { containerRef, zoom }
      },
      template: '<div ref="containerRef" style="width: 800px; height: 600px;"></div>',
    })

    const wrapper = mount(Comp, { attachTo: document.body })
    return { wrapper, containerRef, zoom }
  }

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('initializes with default 100% scale and un-zoomed state', () => {
    const { wrapper, zoom } = createTestViewer()
    expect(zoom.scale.value).toBe(1)
    expect(zoom.translateX.value).toBe(0)
    expect(zoom.translateY.value).toBe(0)
    expect(zoom.isZoomed.value).toBe(false)
    expect(zoom.zoomPercent.value).toBe(100)
    wrapper.unmount()
  })

  it('zooms in, zooms out and clamps between 1x and 5x', () => {
    const { wrapper, zoom } = createTestViewer({ zoomStep: 0.5 })

    zoom.zoomIn()
    expect(zoom.scale.value).toBe(1.5)
    expect(zoom.isZoomed.value).toBe(true)
    expect(zoom.zoomPercent.value).toBe(150)

    zoom.zoomOut()
    expect(zoom.scale.value).toBe(1)
    expect(zoom.isZoomed.value).toBe(false)

    // Cannot zoom below 1
    zoom.zoomOut()
    expect(zoom.scale.value).toBe(1)

    // Zooming up to max
    zoom.setScale(10)
    expect(zoom.scale.value).toBe(5)
    expect(zoom.zoomPercent.value).toBe(500)

    // Reset zoom
    zoom.resetZoom()
    expect(zoom.scale.value).toBe(1)
    expect(zoom.translateX.value).toBe(0)
    expect(zoom.translateY.value).toBe(0)

    wrapper.unmount()
  })

  it('handles zoom wheel with deltaY', () => {
    const { wrapper, zoom } = createTestViewer()

    // Wheel up (zoom in)
    const zoomInEvent = new WheelEvent('wheel', { deltaY: -100, clientX: 400, clientY: 300 })
    zoom.handleZoomWheel(zoomInEvent)
    expect(zoom.scale.value).toBeGreaterThan(1)
    expect(zoom.isZoomed.value).toBe(true)

    // Wheel down (zoom out)
    const zoomOutEvent = new WheelEvent('wheel', { deltaY: 200, clientX: 400, clientY: 300 })
    zoom.handleZoomWheel(zoomOutEvent)
    expect(zoom.scale.value).toBe(1)
    expect(zoom.isZoomed.value).toBe(false)

    wrapper.unmount()
  })

  it('supports drag and pan only when zoomed in and does not block clicks', () => {
    const { wrapper, zoom } = createTestViewer()

    // Try drag when not zoomed -> should not drag and wasDragging is always false
    zoom.onMouseDown(new MouseEvent('mousedown', { button: 0, clientX: 100, clientY: 100 }))
    expect(zoom.isPanning.value).toBe(false)
    expect(zoom.wasDragging()).toBe(false)

    // Zoom in
    zoom.setScale(2)
    expect(zoom.isZoomed.value).toBe(true)

    // Click jitter (< 8px movement) should NOT count as dragging
    zoom.onMouseDown(new MouseEvent('mousedown', { button: 0, clientX: 100, clientY: 100 }))
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 103, clientY: 102 }))
    window.dispatchEvent(new MouseEvent('mouseup'))
    expect(zoom.wasDragging()).toBe(false)

    // Genuine drag (> 8px)
    zoom.onMouseDown(new MouseEvent('mousedown', { button: 0, clientX: 100, clientY: 100 }))
    expect(zoom.isPanning.value).toBe(true)
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 150, clientY: 120 }))
    window.dispatchEvent(new MouseEvent('mouseup'))
    expect(zoom.isPanning.value).toBe(false)

    // wasDragging() returns true ONCE to suppress the click from this drag...
    expect(zoom.wasDragging()).toBe(true)
    // ...and immediately resets so subsequent clicks are never blocked
    expect(zoom.wasDragging()).toBe(false)

    // Resetting zoom guarantees wasDragging is false
    zoom.resetZoom()
    expect(zoom.wasDragging()).toBe(false)

    wrapper.unmount()
  })

  it('responds to keyboard shortcuts +, -, 0', () => {
    const { wrapper, zoom } = createTestViewer()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: '+' }))
    expect(zoom.scale.value).toBeGreaterThan(1)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: '-' }))
    expect(zoom.scale.value).toBe(1)

    zoom.setScale(3)
    expect(zoom.scale.value).toBe(3)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '0' }))
    expect(zoom.scale.value).toBe(1)

    wrapper.unmount()
  })
})
