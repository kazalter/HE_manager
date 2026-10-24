import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useZoomScroller, type ZoomScrollerOptions } from '../composables/useZoomScroller'

// A scroller with a simulated layout: the content is `base` at --he-zoom 1, every size
// scales with --he-zoom, it is centred while smaller than the viewport, and the live
// transform is ignored by layout (as in a browser).
function surface(view = { width: 400, height: 800 }, base = { width: 400, height: 600 }, centered = true) {
  const scroller = document.createElement('div'), content = document.createElement('div')
  scroller.append(content)
  const level = () => Number(content.style.getPropertyValue('--he-zoom') || 1)
  const size = () => ({ width: base.width * level(), height: base.height * level() })
  const offset = (axis: 'width' | 'height') => centered ? Math.max(0, (view[axis] - size()[axis]) / 2) : 0
  let left = 0, top = 0
  const maxLeft = () => Math.max(0, offset('width') + size().width - view.width)
  const maxTop = () => Math.max(0, offset('height') + size().height - view.height)
  Object.defineProperties(scroller, {
    clientWidth: { get: () => view.width }, clientHeight: { get: () => view.height },
    scrollLeft: { get: () => left, set: (value: number) => { left = Math.max(0, Math.min(maxLeft(), value)) }, configurable: true },
    scrollTop: { get: () => top, set: (value: number) => { top = Math.max(0, Math.min(maxTop(), value)) }, configurable: true },
  })
  Object.defineProperties(content, { offsetWidth: { get: () => size().width }, offsetHeight: { get: () => size().height } })
  scroller.getBoundingClientRect = () => ({ left: 0, top: 0, width: view.width, height: view.height }) as DOMRect
  content.getBoundingClientRect = () => ({ left: offset('width') - left, top: offset('height') - top, ...size() }) as DOMRect
  // Where a content point (at zoom 1) currently appears on screen, including the live transform.
  const screenOf = (x: number, y: number) => {
    const match = /translate\(([-\d.e]+)px, ([-\d.e]+)px\) scale\(([\d.e]+)\)/.exec(content.style.transform)
    if (content.style.transform && !match) throw new Error(`unparsed transform ${content.style.transform}`)
    const [tx, ty, k] = match ? [Number(match[1]), Number(match[2]), Number(match[3])] : [0, 0, 1]
    return { x: offset('width') - left + tx + k * x * level(), y: offset('height') - top + ty + k * y * level() }
  }
  return { scroller, content, screenOf }
}

let frames: FrameRequestCallback[] = []
let now = 0
const flushFrames = (limit = 400) => {
  for (let index = 0; index < limit && frames.length; index++) {
    now += 16
    const next = frames; frames = []
    next.forEach(callback => callback(now))
  }
}
const touches = (points: number[][]) => points.map(([clientX, clientY]) => ({ clientX, clientY }))
const touchEvent = (points: number[][], changed: number[][] = [], type = 'touchmove') => ({
  type, touches: touches(points), changedTouches: touches(changed), cancelable: true, preventDefault: vi.fn(),
}) as unknown as TouchEvent

let wrapper: ReturnType<typeof mount> | undefined
function create(options: Partial<ZoomScrollerOptions> = {}, layout = surface()) {
  let zoom!: ReturnType<typeof useZoomScroller>
  wrapper = mount(defineComponent({
    setup() {
      zoom = useZoomScroller({
        scroller: ref(layout.scroller), content: ref(layout.content), centered: true,
        applyScale: (content, scale) => content.style.setProperty('--he-zoom', String(scale)),
        doubleTapScale: () => 2.5, ...options,
      })
      return () => h('div')
    },
  }), { attachTo: document.body })
  return { zoom, ...layout }
}
const pinch = (zoom: ReturnType<typeof useZoomScroller>, from: number[][], to: number[][], steps = 6) => {
  zoom.onTouchStart(touchEvent(from, [], 'touchstart'))
  for (let step = 1; step <= steps; step++) {
    const t = step / steps
    zoom.onTouchMove(touchEvent(from.map((point, index) => point.map((value, axis) => value + (to[index]![axis]! - value) * t))))
    flushFrames(1)
  }
}
const release = (zoom: ReturnType<typeof useZoomScroller>, last: number[][]) => {
  zoom.onTouchEnd(touchEvent([], last, 'touchend'))
}

beforeEach(() => {
  frames = []; now = 0
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { frames.push(callback); return frames.length })
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => { frames = [] })
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks(); vi.useRealTimers() })

describe('pinch', () => {
  it('keeps the content under the fingers in place, live and after committing a real layout', () => {
    const { zoom, scroller, content, screenOf } = create()
    // The content point under the midpoint (200, 400) is (200, 300): the page is centred 100px down.
    pinch(zoom, [[150, 400], [250, 400]], [[100, 400], [300, 400]])
    expect(screenOf(200, 300).x).toBeCloseTo(200)
    expect(screenOf(200, 300).y).toBeCloseTo(400)
    // While the fingers move, only a transform changes and native scrolling is frozen.
    expect(content.style.getPropertyValue('--he-zoom')).toBe('1')
    expect(content.style.willChange).toBe('transform')
    expect(scroller.style.overflowX).toBe('hidden')
    release(zoom, [[100, 400], [300, 400]])
    flushFrames()
    expect(zoom.scale.value).toBeCloseTo(2)
    expect(content.style.transform).toBe('')
    expect(content.style.willChange).toBe('')
    // Panning the enlarged page is the scroller's own scrolling.
    expect(scroller.style.overflowX).toBe('auto')
    expect(scroller.scrollLeft).toBeCloseTo(200)
    expect(scroller.scrollTop).toBeCloseTo(200)
    expect(screenOf(200, 300).x).toBeCloseTo(200)
    expect(screenOf(200, 300).y).toBeCloseTo(400)
  })

  it('follows a moving midpoint as a two-finger pan', () => {
    const { zoom, screenOf } = create()
    pinch(zoom, [[150, 400], [250, 400]], [[130, 460], [330, 460]])
    // Scaled 2x about the starting point, then carried 30px right and 60px down with the fingers.
    expect(screenOf(200, 300).x).toBeCloseTo(230)
    expect(screenOf(200, 300).y).toBeCloseTo(460)
  })

  it('resists below fit and springs back to a centred page', () => {
    const { zoom, scroller, screenOf } = create()
    pinch(zoom, [[100, 400], [300, 400]], [[180, 400], [220, 400]])
    const shrunk = screenOf(400, 600).x - screenOf(0, 0).x
    // A fifth of the finger distance shrinks far less than a fifth.
    expect(shrunk).toBeLessThan(400)
    expect(shrunk).toBeGreaterThan(400 * 0.45)
    release(zoom, [[180, 400], [220, 400]])
    flushFrames()
    expect(zoom.scale.value).toBe(1)
    expect(scroller.style.overflowX).toBe('')
    expect(screenOf(0, 0)).toEqual({ x: 0, y: 100 })
  })

  it('resists past the maximum and settles at it', () => {
    const { zoom } = create({ maxScale: () => 3 })
    pinch(zoom, [[190, 400], [210, 400]], [[10, 400], [390, 400]])
    release(zoom, [[10, 400], [390, 400]])
    flushFrames()
    expect(zoom.scale.value).toBe(3)
  })

  it('reverses immediately at a limit because the fingers map to one resisted scale', () => {
    const { zoom, screenOf } = create()
    pinch(zoom, [[100, 400], [300, 400]], [[190, 400], [210, 400]])
    const smallest = screenOf(400, 0).x - screenOf(0, 0).x
    zoom.onTouchMove(touchEvent([[185, 400], [215, 400]])); flushFrames(1)
    expect(screenOf(400, 0).x - screenOf(0, 0).x).toBeGreaterThan(smallest)
  })

  it('brings an overshooting pan back inside the enlarged page instead of jumping on commit', () => {
    const { zoom, scroller, screenOf } = create()
    // Spread at the left edge and drag the pair far right: the page's left edge leaves the viewport edge.
    pinch(zoom, [[20, 400], [120, 400]], [[200, 400], [400, 400]])
    release(zoom, [[200, 400], [400, 400]])
    flushFrames()
    expect(zoom.scale.value).toBeCloseTo(2)
    expect(scroller.scrollLeft).toBe(0)
    expect(screenOf(0, 0).x).toBeCloseTo(0)
  })

  it('suppresses the click after a pinch but not a later deliberate tap', () => {
    const { zoom } = create()
    pinch(zoom, [[150, 400], [250, 400]], [[100, 400], [300, 400]])
    release(zoom, [[100, 400], [300, 400]])
    expect(zoom.wasGesture()).toBe(true)
    expect(zoom.wasGesture()).toBe(false)
    pinch(zoom, [[150, 400], [250, 400]], [[160, 400], [240, 400]])
    release(zoom, [[160, 400], [240, 400]])
    // Browsers send no click after a pinch; the next touch must not inherit its suppression.
    zoom.onTouchStart(touchEvent([[200, 400]], [], 'touchstart'))
    zoom.onTouchEnd(touchEvent([], [[200, 400]], 'touchend'))
    expect(zoom.wasGesture()).toBe(false)
  })

  it('blocks native moves only while two fingers are down', () => {
    const { zoom, scroller } = create()
    const add = vi.spyOn(scroller, 'addEventListener'), remove = vi.spyOn(scroller, 'removeEventListener')
    zoom.onTouchStart(touchEvent([[200, 400]], [], 'touchstart'))
    expect(add).not.toHaveBeenCalled()
    pinch(zoom, [[150, 400], [250, 400]], [[100, 400], [300, 400]])
    expect(add).toHaveBeenCalledWith('touchmove', expect.any(Function), { passive: false })
    release(zoom, [[100, 400], [300, 400]])
    expect(remove).toHaveBeenCalledWith('touchmove', add.mock.calls[0]![1])
  })
})

describe('double-tap', () => {
  const tap = (zoom: ReturnType<typeof useZoomScroller>, x: number, y: number) => {
    zoom.onTouchStart(touchEvent([[x, y]], [], 'touchstart'))
    zoom.onTouchEnd(touchEvent([], [[x, y]], 'touchend'))
  }

  it('zooms in around the tapped point and back out, swallowing the synthetic dblclick', () => {
    const onDoubleTap = vi.fn()
    const { zoom, screenOf } = create({ onDoubleTap })
    tap(zoom, 300, 500)
    expect(zoom.wasGesture()).toBe(false)
    tap(zoom, 302, 501)
    expect(onDoubleTap).toHaveBeenCalledOnce()
    expect(zoom.wasDoubleTap()).toBe(true)
    expect(zoom.wasDoubleTap()).toBe(false)
    flushFrames()
    expect(zoom.scale.value).toBe(2.5)
    // The content point under the second tap, (302, 401), stays under the finger.
    expect(screenOf(302, 401).x).toBeCloseTo(302)
    expect(screenOf(302, 401).y).toBeCloseTo(501)
    tap(zoom, 200, 400); tap(zoom, 200, 400)
    flushFrames()
    expect(zoom.scale.value).toBe(1)
  })

  it('finishes a running zoom at its target when the page is touched again', () => {
    const { zoom } = create()
    tap(zoom, 200, 400); tap(zoom, 200, 400)
    flushFrames(2)
    zoom.onTouchStart(touchEvent([[200, 400]], [], 'touchstart'))
    expect(zoom.scale.value).toBe(2.5)
    expect(zoom.isGesturing.value).toBe(false)
  })

  it('ignores taps that moved or were slow', () => {
    vi.spyOn(performance, 'now').mockImplementation(() => now)
    const { zoom } = create()
    tap(zoom, 200, 400)
    zoom.onTouchStart(touchEvent([[200, 400]], [], 'touchstart'))
    zoom.onTouchMove(touchEvent([[200, 430]]))
    zoom.onTouchEnd(touchEvent([], [[200, 430]], 'touchend'))
    flushFrames()
    expect(zoom.scale.value).toBe(1)
  })
})

describe('swipes, wheel, keys and mouse', () => {
  it('reports a horizontal flick only at fit, never after a pinch', () => {
    const onSwipe = vi.fn()
    const { zoom } = create({ onSwipe })
    pinch(zoom, [[100, 400], [300, 400]], [[180, 400], [220, 400]])
    zoom.onTouchEnd(touchEvent([[220, 400]], [[180, 400]], 'touchend'))
    zoom.onTouchMove(touchEvent([[330, 400]]))
    zoom.onTouchEnd(touchEvent([], [[330, 400]], 'touchend'))
    flushFrames()
    expect(onSwipe).not.toHaveBeenCalled()
    zoom.onTouchStart(touchEvent([[300, 400]], [], 'touchstart'))
    zoom.onTouchMove(touchEvent([[200, 405]]))
    zoom.onTouchEnd(touchEvent([], [[200, 405]], 'touchend'))
    expect(onSwipe).toHaveBeenCalledExactlyOnceWith(1)
    expect(zoom.wasGesture()).toBe(true)
  })

  it('follows ctrl+wheel streams directly and commits once they stop', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const { zoom, content, screenOf } = create()
    const wheel = () => zoom.handleWheelZoom({ deltaY: -120, deltaMode: 0, ctrlKey: true, clientX: 200, clientY: 400, preventDefault: vi.fn() } as unknown as WheelEvent)
    wheel(); flushFrames(1); wheel(); flushFrames(1)
    expect(content.style.transform).toContain('scale(1.6')
    expect(zoom.scale.value).toBe(1)
    expect(screenOf(200, 300).y).toBeCloseTo(400)
    vi.advanceTimersByTime(200); flushFrames()
    expect(zoom.scale.value).toBeCloseTo(Math.exp(0.48))
    expect(zoom.zoomPercent.value).toBe(Math.round(Math.exp(0.48) * 100))
  })

  it('zooms with + - 0 only while the surface is active', () => {
    let active = true
    const { zoom } = create({ keyboard: () => active })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '+' })); flushFrames()
    expect(zoom.scale.value).toBe(1.25)
    active = false
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '+' })); flushFrames()
    expect(zoom.scale.value).toBe(1.25)
    active = true
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '0' })); flushFrames()
    expect(zoom.scale.value).toBe(1)
  })

  it('pans a zoomed page by mouse drag and suppresses the following click once', () => {
    const { zoom, scroller } = create()
    zoom.zoomTo(3, undefined, undefined, false)
    const left = scroller.scrollLeft, top = scroller.scrollTop
    zoom.onMouseDown(new MouseEvent('mousedown', { button: 0, clientX: 200, clientY: 400 }))
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 150, clientY: 340 }))
    expect(zoom.isDragging.value).toBe(true)
    window.dispatchEvent(new MouseEvent('mouseup'))
    expect([scroller.scrollLeft, scroller.scrollTop]).toEqual([left + 50, top + 60])
    expect(zoom.wasGesture()).toBe(true)
    expect(zoom.wasGesture()).toBe(false)
  })

  it('pins a column to its start and keeps the scroll inside it when zooming back out', () => {
    const { zoom, scroller, screenOf } = create({ centered: false }, surface({ width: 400, height: 800 }, { width: 400, height: 6000 }, false))
    scroller.scrollTop = 5200
    zoom.zoomTo(2, 200, 700, false)
    expect(screenOf(200, 5900).y).toBeCloseTo(700)
    expect(scroller.scrollLeft).toBeCloseTo(200)
    zoom.zoomTo(1, 50, 100, false)
    expect(scroller.scrollLeft).toBe(0)
    expect(scroller.scrollTop).toBeLessThanOrEqual(5200)
    expect(screenOf(0, 6000).y).toBeGreaterThanOrEqual(800)
  })
})
