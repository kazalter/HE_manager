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
  const viewport = document.createElement('div'), content = document.createElement('div')
  Object.defineProperties(viewport, { clientWidth: { value: 400 }, clientHeight: { value: 600 } })
  Object.defineProperty(content, 'offsetHeight', { value: 5000 })
  vi.spyOn(viewport, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 400, height: 600 } as DOMRect)
  viewport.scrollTop = 1000
  let zoom!: ReturnType<typeof useWebtoonZoom>
  wrapper = mount(defineComponent({ setup() { zoom = useWebtoonZoom(ref(viewport), ref(content)); return () => null } }))
  return { zoom, viewport }
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
  const { zoom, viewport } = create()
  zoom.onTouchStart(touch([[100, 300], [300, 300]], 'touchstart'))
  zoom.onTouchMove(touch([[0, 300], [400, 300]])); await nextTick()
  expect(zoom.scale.value).toBe(2)
  expect(viewport.scrollTop).toBe(2300)
  expect(zoom.translateX.value).toBe(-200)
  expect(zoom.spaceStyle.value.height).toBe('10000px')
  zoom.onTouchEnd(touch([[200, 300]], 'touchend'))
  zoom.onTouchMove(touch([[220, 250]])); await nextTick()
  expect(zoom.translateX.value).toBe(-180)
  expect(viewport.scrollTop).toBe(2350)
  zoom.onTouchEnd(touch([], 'touchend'))
  zoom.reset(); await nextTick()
  expect(zoom.scale.value).toBe(1)
  expect(viewport.scrollTop).toBe(1175)
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

it('cancels pending scroll writes when the reader closes', async () => {
  const { zoom, viewport } = create()
  zoom.onTouchStart(touch([[100, 300], [300, 300]], 'touchstart'))
  zoom.onTouchMove(touch([[0, 300], [400, 300]]))
  wrapper!.unmount(); wrapper = undefined
  await nextTick()
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
