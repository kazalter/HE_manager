import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, ref, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { useWebtoonZoom } from '../composables/useWebtoonZoom'

let wrapper: ReturnType<typeof mount> | undefined
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks() })
const touch = (points: number[][], type = 'touchmove') => ({
  type, touches: points.map(([clientX, clientY]) => ({ clientX, clientY })), cancelable: true, preventDefault: vi.fn(),
}) as unknown as TouchEvent
function create() {
  const viewport = document.createElement('div'), space = document.createElement('div'), content = document.createElement('div')
  space.append(content)
  Object.defineProperties(viewport, { clientWidth: { value: 400 }, clientHeight: { value: 600 } })
  Object.defineProperty(content, 'offsetHeight', { get: () => 5000, configurable: true })
  vi.spyOn(viewport, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 400, height: 600 } as DOMRect)
  viewport.scrollTop = 1000
  let zoom!: ReturnType<typeof useWebtoonZoom>
  wrapper = mount(defineComponent({ setup() { zoom = useWebtoonZoom(ref(viewport), ref(content)); return () => null } }))
  return { zoom, viewport, space, content }
}

it('clamps to 100% while fingers are still down, with no change or rebound on release', async () => {
  const { zoom, viewport } = create()
  zoom.onTouchStart(touch([[100, 300], [300, 300]], 'touchstart'))
  zoom.onTouchMove(touch([[180, 300], [220, 300]])); await nextTick()
  expect(zoom.scale.value).toBe(1)
  expect(viewport.scrollLeft).toBe(0)
  expect(viewport.scrollTop).toBe(1000)
  zoom.onTouchMove(touch([[190, 300], [210, 300]])); await nextTick()
  expect(zoom.scale.value).toBe(1)
  zoom.onTouchEnd(touch([], 'touchend')); await nextTick()
  expect(zoom.scale.value).toBe(1)
  expect(zoom.isInteracting.value).toBe(false)
  expect(viewport.scrollTop).toBe(1000)
})

it('anchors the content under the pinch and maintains the enlarged scroll extent', async () => {
  const { zoom, viewport, space, content } = create()
  zoom.onTouchStart(touch([[100, 300], [300, 300]], 'touchstart'))
  zoom.onTouchMove(touch([[0, 300], [400, 300]]))
  // Extent, transform and both scroll axes land together, without waiting for a Vue flush.
  expect(zoom.scale.value).toBe(2)
  expect(viewport.scrollTop).toBe(2300)
  expect(viewport.scrollLeft).toBe(200)
  expect(space.style.width).toBe('800px')
  expect(space.style.height).toBe('10000px')
  expect(content.style.position).toBe('absolute')
  expect(content.style.width).toBe('400px')
  expect(content.style.transform).toBe('scale(2)')
  expect(content.style.willChange).toBe('transform')
  expect(viewport.style.touchAction).toBe('none')
  zoom.onTouchEnd(touch([[200, 300]], 'touchend'))
  zoom.onTouchMove(touch([[220, 250]])); await nextTick()
  expect(viewport.scrollLeft).toBe(180)
  expect(viewport.scrollTop).toBe(2350)
  zoom.onTouchEnd(touch([], 'touchend'))
  expect(content.style.willChange).toBe('')
  zoom.reset()
  expect(zoom.scale.value).toBe(1)
  expect(viewport.scrollTop).toBe(1175)
  expect(viewport.scrollLeft).toBe(0)
  expect(space.style.width).toBe('')
  expect(space.style.height).toBe('')
  expect(content.style.position).toBe('')
  expect(content.style.width).toBe('')
  expect(content.style.transform).toBe('')
  expect(viewport.style.touchAction).toBe('pan-y')
})

it('keeps the pinch anchor exact even when the browser rounds scroll offsets', () => {
  const { zoom, viewport } = create()
  let left = 0
  Object.defineProperty(viewport, 'scrollLeft', { get: () => left, set: (value: number) => { left = Math.round(value) }, configurable: true })
  zoom.onTouchStart(touch([[150, 300], [250, 300]], 'touchstart'))
  // Many tiny pinch steps around x = 200 must not accumulate rounding drift.
  for (let step = 1; step <= 40; step++) zoom.onTouchMove(touch([[150 - step * 0.7, 300], [250 + step * 0.7, 300]]))
  const exact = 200 * (zoom.scale.value - 1)
  expect(Math.abs(left - exact)).toBeLessThanOrEqual(0.5)
})

it('keeps normal one-finger scrolling native and reverses immediately after reaching the zoom limit', async () => {
  const { zoom } = create()
  const start = touch([[100, 300]], 'touchstart'), move = touch([[100, 200]])
  zoom.onTouchStart(start); zoom.onTouchMove(move)
  expect(start.preventDefault).not.toHaveBeenCalled()
  expect(move.preventDefault).not.toHaveBeenCalled()
  zoom.onTouchStart(touch([[100, 300], [300, 300]], 'touchstart'))
  zoom.onTouchMove(touch([[190, 300], [210, 300]]))
  zoom.onTouchMove(touch([[185, 300], [215, 300]])); await nextTick()
  expect(zoom.scale.value).toBe(1.5)
})

it('does no zoom layout reads or scroll writes during normal one-finger reading', async () => {
  const { zoom, viewport, space, content } = create()
  const height = vi.spyOn(content, 'offsetHeight', 'get')
  const scroll = vi.spyOn(viewport, 'scrollTop', 'set'), scrollLeft = vi.spyOn(viewport, 'scrollLeft', 'set')
  zoom.onTouchStart(touch([[100, 300]], 'touchstart'))
  zoom.onTouchMove(touch([[100, 200]]))
  zoom.onPassiveTouchMove(touch([[100, 100]]))
  zoom.onTouchEnd(touch([], 'touchend')); await nextTick()
  expect(viewport.getBoundingClientRect).not.toHaveBeenCalled()
  expect(height).not.toHaveBeenCalled()
  expect(scroll).not.toHaveBeenCalled()
  expect(scrollLeft).not.toHaveBeenCalled()
  expect(space.style.height).toBe('')
  expect(content.style.position).toBe('')
  expect(content.style.transform).toBe('')
})

it('only installs a blocking move listener during a pinch, and cleans it up on end or unmount', async () => {
  const { zoom, viewport } = create()
  const add = vi.spyOn(viewport, 'addEventListener'), remove = vi.spyOn(viewport, 'removeEventListener')
  zoom.onTouchStart(touch([[100, 300]], 'touchstart'))
  expect(add).not.toHaveBeenCalled()
  const pinch = touch([[100, 300], [300, 300]], 'touchstart')
  zoom.onTouchStart(pinch)
  expect(pinch.preventDefault).not.toHaveBeenCalled()
  expect(add).toHaveBeenCalledWith('touchmove', zoom.onTouchMove, { passive: false })
  zoom.onTouchEnd(touch([], 'touchend'))
  expect(remove).toHaveBeenCalledWith('touchmove', zoom.onTouchMove)
  zoom.onTouchStart(pinch)
  remove.mockClear()
  wrapper!.unmount(); wrapper = undefined
  expect(remove).toHaveBeenCalledWith('touchmove', zoom.onTouchMove)
})

const zoomIn = async (zoom: ReturnType<typeof useWebtoonZoom>) => {
  zoom.onTouchStart(touch([[100, 300], [300, 300]], 'touchstart'))
  zoom.onTouchMove(touch([[0, 300], [400, 300]])); await nextTick()
  zoom.onTouchEnd(touch([], 'touchend'))
}

it('moves an enlarged column freely on both axes, whichever way the drag starts', async () => {
  const { zoom, viewport, content } = create()
  await zoomIn(zoom)
  // Native touch scrolling would lock the drag to the axis it starts on.
  expect(viewport.style.touchAction).toBe('none')
  const styles = content.style.cssText
  for (const path of [[[200, 300], [140, 300], [140, 180]], [[200, 300], [200, 240], [260, 220]], [[200, 300], [230, 255]]]) {
    const left = viewport.scrollLeft, top = viewport.scrollTop
    zoom.onTouchStart(touch([path[0]!], 'touchstart'))
    for (const point of path.slice(1)) {
      const move = touch([point])
      zoom.onPassiveTouchMove(move)
      expect(move.preventDefault).not.toHaveBeenCalled()
    }
    const [endX, endY] = path.at(-1)!
    // Both axes follow the finger exactly, in the same frame.
    expect(viewport.scrollLeft).toBe(left - (endX! - path[0]![0]!))
    expect(viewport.scrollTop).toBe(top - (endY! - path[0]![1]!))
    zoom.onTouchEnd(touch([], 'touchend'))
  }
  // A drag only scrolls: no style writes, no layer promotion churn.
  expect(content.style.cssText).toBe(styles)
  expect(content.style.willChange).toBe('')
  expect(zoom.isInteracting.value).toBe(false)
})

it('stops a drag at the edges of the enlarged column', async () => {
  const { zoom, viewport } = create()
  await zoomIn(zoom)
  zoom.onTouchStart(touch([[200, 300]], 'touchstart'))
  zoom.onPassiveTouchMove(touch([[900, -9000]]))
  expect(viewport.scrollLeft).toBe(0)
  expect(viewport.scrollTop).toBe(10000 - 600)
  zoom.onPassiveTouchMove(touch([[-900, 9000]]))
  expect(viewport.scrollLeft).toBe(400)
  expect(viewport.scrollTop).toBe(0)
})

describe('momentum after releasing a drag on the enlarged column', () => {
  let now = 0
  const frames: FrameRequestCallback[] = []
  const flick = (zoom: ReturnType<typeof useWebtoonZoom>, pauseBeforeLift = 0) => {
    zoom.onTouchStart(touch([[300, 500]], 'touchstart'))
    for (let step = 1; step <= 5; step++) { now += 16; zoom.onPassiveTouchMove(touch([[300 - step * 10, 500 - step * 20]])) }
    now += pauseBeforeLift
    zoom.onTouchEnd(touch([], 'touchend'))
  }
  beforeEach(() => {
    now = 0; frames.length = 0
    vi.spyOn(performance, 'now').mockImplementation(() => now)
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => frames.push(callback))
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => { frames.length = 0 })
  })

  it('glides on both axes with a decaying step, and a new touch catches it', async () => {
    const { zoom, viewport } = create()
    await zoomIn(zoom)
    flick(zoom)
    let left = viewport.scrollLeft, top = viewport.scrollTop, previous = Infinity
    for (let frame = 0; frame < 5; frame++) {
      now += 16; frames.shift()!(now)
      const stepX = viewport.scrollLeft - left, stepY = viewport.scrollTop - top
      expect(stepX).toBeGreaterThan(0)
      expect(stepY).toBeCloseTo(stepX * 2)
      expect(stepY).toBeLessThan(previous)
      previous = stepY; left = viewport.scrollLeft; top = viewport.scrollTop
    }
    zoom.onTouchStart(touch([[200, 300]], 'touchstart'))
    expect(frames).toHaveLength(0)
  })

  it('does not throw the column when the finger rests before lifting', async () => {
    const { zoom } = create()
    await zoomIn(zoom)
    flick(zoom, 200)
    expect(frames).toHaveLength(0)
  })

  it('yields as soon as something else scrolls the column', async () => {
    const { zoom, viewport } = create()
    await zoomIn(zoom)
    flick(zoom)
    now += 16; frames.shift()!(now)
    viewport.scrollTop += 300
    const top = viewport.scrollTop
    now += 16; frames.shift()!(now)
    expect(viewport.scrollTop).toBe(top)
    expect(frames).toHaveLength(0)
  })
})

it('leaves the scroll position alone when resetting an unzoomed column', () => {
  const { zoom, viewport } = create()
  const scroll = vi.spyOn(viewport, 'scrollTop', 'set')
  zoom.reset()
  expect(scroll).not.toHaveBeenCalled()
  expect(viewport.scrollTop).toBe(1000)
})

it('continues vertical movement with the remaining finger after shrinking to normal', async () => {
  const { zoom, viewport } = create()
  zoom.onTouchStart(touch([[100, 300], [300, 300]], 'touchstart'))
  zoom.onTouchMove(touch([[190, 300], [210, 300]])); await nextTick()
  zoom.onTouchEnd(touch([[200, 300]], 'touchend'))
  const move = touch([[200, 200]])
  zoom.onTouchMove(move); await nextTick()
  expect(move.preventDefault).toHaveBeenCalledOnce()
  expect(viewport.scrollTop).toBe(1100)
  zoom.onTouchEnd(touch([], 'touchend'))
  expect(zoom.isInteracting.value).toBe(false)
})
