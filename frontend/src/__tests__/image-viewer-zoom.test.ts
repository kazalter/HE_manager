import { describe, it, expect, afterEach, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
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
    vi.restoreAllMocks()
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

  it('keeps sub-percent pinch changes and follows a moving two-finger midpoint', () => {
    const { wrapper, zoom, containerRef } = createTestViewer()
    const rect = { left: 0, top: 0, width: 400, height: 600 } as DOMRect
    const bounds = vi.spyOn(containerRef.value!, 'getBoundingClientRect').mockReturnValue(rect)
    const touch = (points: number[][]) => ({ touches: points.map(([clientX, clientY]) => ({ clientX, clientY })), cancelable: true, preventDefault: vi.fn() }) as unknown as TouchEvent
    zoom.setScale(2)
    zoom.onTouchStart(touch([[150, 250], [250, 250]]))
    zoom.onTouchMove(touch([[170, 270], [270, 270]]))
    expect(zoom.translateX.value).toBeCloseTo(20)
    expect(zoom.translateY.value).toBeCloseTo(20)
    zoom.onTouchMove(touch([[170, 270], [270.1, 270]]))
    expect(zoom.scale.value).toBeCloseTo(2.002, 6)
    expect(bounds).toHaveBeenCalledTimes(2) // setScale and gesture start, no layout reads per move.
    wrapper.unmount()
  })

  it('resists past the minimum during the pinch, reverses immediately and springs back on release', () => {
    const { wrapper, zoom } = createTestViewer()
    const touch = (points: number[][], changed: number[][] = []) => ({
      touches: points.map(([clientX, clientY]) => ({ clientX, clientY })),
      changedTouches: changed.map(([clientX, clientY]) => ({ clientX, clientY })),
      cancelable: true, preventDefault: vi.fn(),
    }) as unknown as TouchEvent
    zoom.onTouchStart(touch([[100, 100], [300, 100]]))
    zoom.onTouchMove(touch([[190, 100], [210, 100]]))
    // A tenth of the finger distance only shrinks to the rubber-band floor.
    expect(zoom.scale.value).toBeLessThan(1)
    expect(zoom.scale.value).toBeGreaterThanOrEqual(0.75)
    const shrunk = zoom.scale.value
    zoom.onTouchMove(touch([[185, 100], [215, 100]]))
    expect(zoom.scale.value).toBeCloseTo(shrunk * 1.5)
    zoom.onTouchMove(touch([[195, 100], [205, 100]]))
    zoom.onTouchEnd(touch([], [[195, 100], [205, 100]]))
    expect(zoom.scale.value).toBe(1)
    expect(zoom.zoomPercent.value).toBe(100)
    expect(zoom.wasTouchGesture()).toBe(true)
    wrapper.unmount()
  })

  const mountWithContent = (options = {}) => {
    let zoom!: ReturnType<typeof useImageViewerZoom>
    const containerRef = ref<HTMLDivElement | null>(null), contentRef = ref<HTMLDivElement | null>(null)
    const renders = vi.fn()
    const Comp = defineComponent({
      setup() {
        zoom = useImageViewerZoom(containerRef, { contentRef, ...options })
        return () => { renders(); return h('div', { ref: containerRef }, [h('div', { ref: contentRef })]) }
      },
    })
    const wrapper = mount(Comp, { attachTo: document.body })
    vi.spyOn(containerRef.value!, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 400, height: 800 } as DOMRect)
    return { wrapper, zoom, content: contentRef.value!, renders }
  }
  const touchAt = (points: number[][], changed: number[][] = []) => ({
    type: 'touchmove',
    touches: points.map(([clientX, clientY]) => ({ clientX, clientY })),
    changedTouches: changed.map(([clientX, clientY]) => ({ clientX, clientY })),
    cancelable: true, preventDefault: vi.fn(),
  }) as unknown as TouchEvent

  it('writes the transform directly, compositing only while the fingers move', async () => {
    const { wrapper, zoom, content, renders } = mountWithContent()
    await nextTick()
    renders.mockClear()
    zoom.onTouchStart(touchAt([[100, 400], [300, 400]]))
    zoom.onTouchMove(touchAt([[50, 400], [350, 400]]))
    zoom.onTouchMove(touchAt([[0, 400], [400, 400]]))
    expect(content.style.transform).toBe('translate(0px, 0px) scale(2)')
    expect(content.style.transition).toBe('none')
    expect(content.style.willChange).toBe('transform')
    zoom.onTouchEnd(touchAt([], [[0, 400], [400, 400]]))
    expect(content.style.willChange).toBe('')
    expect(zoom.zoomPercent.value).toBe(200)
    await nextTick()
    expect(renders).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('stops panning at the fitted image edges instead of the letterbox', () => {
    // A 400x400 image fitted into a 400x800 container leaves 200px bands above and below.
    const { wrapper, zoom } = mountWithContent({ contentSize: () => ({ width: 400, height: 400 }) })
    zoom.setScale(1.5)
    zoom.onTouchStart(touchAt([[200, 400]]))
    zoom.onTouchMove(touchAt([[300, 600]]))
    expect(zoom.translateX.value).toBe(100)
    // 1.5 x 400 = 600px of image is still shorter than the 800px container.
    expect(zoom.translateY.value).toBe(0)
    wrapper.unmount()
  })

  it('zooms around a double-tap, zooms back out on the next one, and swallows the synthetic dblclick', () => {
    const onDoubleTap = vi.fn()
    const { wrapper, zoom, content } = mountWithContent({ doubleTapScale: 2.5, onDoubleTap })
    const tap = (x: number, y: number) => {
      zoom.onTouchStart(touchAt([[x, y]]))
      zoom.onTouchEnd(touchAt([], [[x, y]]))
    }
    tap(100, 400)
    expect(zoom.scale.value).toBe(1)
    expect(zoom.wasTouchGesture()).toBe(false)
    tap(102, 401)
    expect(zoom.scale.value).toBe(2.5)
    // The tapped point (98px left of centre) stays under the finger.
    expect(zoom.translateX.value).toBeCloseTo(147)
    expect(content.style.transition).not.toBe('none')
    expect(zoom.wasTouchGesture()).toBe(true)
    expect(zoom.wasDoubleTap()).toBe(true)
    expect(zoom.wasDoubleTap()).toBe(false)
    expect(onDoubleTap).toHaveBeenCalledOnce()
    tap(200, 400); tap(200, 400)
    expect(zoom.scale.value).toBe(1)
    expect(zoom.isPanning.value).toBe(false)
    expect(content.style.transition).not.toBe('none')
    expect(content.style.willChange).toBe('')
    wrapper.unmount()
  })

  it('carries a released pan forward with decaying momentum', () => {
    let now = 0
    vi.spyOn(performance, 'now').mockImplementation(() => now)
    const frames: FrameRequestCallback[] = []
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => frames.push(callback))
    const cancel = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
    const { wrapper, zoom } = mountWithContent()
    zoom.setScale(4)
    zoom.onTouchStart(touchAt([[200, 400]]))
    for (let step = 1; step <= 5; step++) { now += 16; zoom.onTouchMove(touchAt([[200 + step * 16, 400]])) }
    const released = zoom.translateX.value
    zoom.onTouchEnd(touchAt([], [[280, 400]]))
    expect(zoom.isPanning.value).toBe(true)
    let previous = released, previousStep = Infinity
    for (let frame = 0; frame < 5; frame++) {
      now += 16; frames.shift()!(now)
      const stepSize = zoom.translateX.value - previous
      expect(stepSize).toBeGreaterThan(0)
      expect(stepSize).toBeLessThan(previousStep)
      previous = zoom.translateX.value; previousStep = stepSize
    }
    // Touching the page again catches it.
    cancel.mockClear()
    zoom.onTouchStart(touchAt([[200, 400]]))
    expect(cancel).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('does not throw the image when the finger rests before lifting', () => {
    let now = 0
    vi.spyOn(performance, 'now').mockImplementation(() => now)
    const raf = vi.spyOn(window, 'requestAnimationFrame')
    const { wrapper, zoom } = mountWithContent()
    zoom.setScale(4)
    zoom.onTouchStart(touchAt([[200, 400]]))
    for (let step = 1; step <= 5; step++) { now += 16; zoom.onTouchMove(touchAt([[200 + step * 16, 400]])) }
    now += 200
    zoom.onTouchEnd(touchAt([], [[280, 400]]))
    expect(raf).not.toHaveBeenCalled()
    expect(zoom.isPanning.value).toBe(false)
    wrapper.unmount()
  })

  it('follows trackpad pinches without easing and updates the label once they settle', () => {
    vi.useFakeTimers()
    const { wrapper, zoom, content } = mountWithContent()
    zoom.handleZoomWheel(new WheelEvent('wheel', { deltaY: -100, ctrlKey: true, clientX: 200, clientY: 400 }))
    zoom.handleZoomWheel(new WheelEvent('wheel', { deltaY: -100, ctrlKey: true, clientX: 200, clientY: 400 }))
    expect(zoom.scale.value).toBeGreaterThan(1.4)
    expect(content.style.transition).toBe('none')
    expect(zoom.zoomPercent.value).toBe(100)
    vi.advanceTimersByTime(200)
    expect(zoom.zoomPercent.value).toBe(Math.round(zoom.scale.value * 100))
    expect(content.style.willChange).toBe('')
    vi.useRealTimers()
    wrapper.unmount()
  })
})
