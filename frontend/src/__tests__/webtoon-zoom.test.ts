import { afterEach, expect, it, vi } from 'vitest'
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
  expect(zoom.translateX.value).toBe(0)
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
  // Extent, transform and scroll position land together, without waiting for a Vue flush.
  expect(zoom.scale.value).toBe(2)
  expect(viewport.scrollTop).toBe(2300)
  expect(zoom.translateX.value).toBe(-200)
  expect(space.style.height).toBe('10000px')
  expect(content.style.position).toBe('absolute')
  expect(content.style.transform).toBe('translate(-200px, 0px) scale(2)')
  expect(content.style.willChange).toBe('transform')
  zoom.onTouchEnd(touch([[200, 300]], 'touchend'))
  zoom.onTouchMove(touch([[220, 250]])); await nextTick()
  expect(zoom.translateX.value).toBe(-180)
  expect(viewport.scrollTop).toBe(2350)
  zoom.onTouchEnd(touch([], 'touchend'))
  expect(content.style.willChange).toBe('')
  zoom.reset()
  expect(zoom.scale.value).toBe(1)
  expect(viewport.scrollTop).toBe(1175)
  expect(space.style.height).toBe('')
  expect(content.style.position).toBe('')
  expect(content.style.transform).toBe('')
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
  const scroll = vi.spyOn(viewport, 'scrollTop', 'set')
  zoom.onTouchStart(touch([[100, 300]], 'touchstart'))
  zoom.onPassiveTouchMove(touch([[100, 200]]))
  zoom.onTouchEnd(touch([], 'touchend')); await nextTick()
  expect(viewport.getBoundingClientRect).not.toHaveBeenCalled()
  expect(height).not.toHaveBeenCalled()
  expect(scroll).not.toHaveBeenCalled()
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

it('preserves native vertical scrolling on a new one-finger gesture while zoomed', async () => {
  const { zoom, viewport } = create()
  zoom.onTouchStart(touch([[100, 300], [300, 300]], 'touchstart'))
  zoom.onTouchMove(touch([[0, 300], [400, 300]])); await nextTick()
  zoom.onTouchEnd(touch([], 'touchend'))
  const top = viewport.scrollTop, move = touch([[220, 200]])
  zoom.onTouchStart(touch([[200, 300]], 'touchstart'))
  zoom.onPassiveTouchMove(move); await nextTick()
  expect(move.preventDefault).not.toHaveBeenCalled()
  expect(viewport.scrollTop).toBe(top)
  expect(zoom.translateX.value).toBe(-180)
  expect(zoom.isInteracting.value).toBe(false)
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
