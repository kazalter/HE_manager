import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { useWebtoonScroller } from '../composables/useWebtoonScroller'

let wrapper: ReturnType<typeof mount> | undefined
let frames: FrameRequestCallback[] = []
const paint = () => { const callbacks = frames; frames = []; callbacks.forEach(callback => callback(0)) }
const event = (points: number[][], type = 'touchmove') => ({ type,
  touches: points.map(([clientX, clientY]) => ({ clientX, clientY })),
  changedTouches: [{ clientX: 200, clientY: 400 }],
}) as unknown as TouchEvent

beforeEach(() => {
  frames = []
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { frames.push(callback); return frames.length })
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => { frames = [] })
  document.head.innerHTML = '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; paint(); paint(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function create() {
  const active = ref(true), onScroll = vi.fn(), onPinchStart = vi.fn()
  const viewport = Object.assign(new EventTarget(), { scale: 1 })
  vi.stubGlobal('visualViewport', viewport)
  const scroller = document.createElement('div'), content = document.createElement('div')
  scroller.append(content)
  let reader!: ReturnType<typeof useWebtoonScroller>
  wrapper = mount(defineComponent({ setup() {
    reader = useWebtoonScroller({ native: active, scroller: ref(scroller), content: ref(content), onScroll, onPinchStart,
      applyScale: (element, scale) => element.style.setProperty('--he-zoom', String(scale)), doubleTapScale: () => 2 })
    return () => h('div')
  } }))
  return { active, onScroll, onPinchStart, viewport, scroller, content, reader }
}

describe('native mobile webtoon', () => {
  it('leaves touch and Safari gestures to the browser without freezing or transforming content', () => {
    const { reader, content, scroller, onPinchStart } = create()
    const listen = vi.spyOn(scroller, 'addEventListener')
    reader.onTouchStart(event([[150, 400], [250, 400]], 'touchstart'))
    reader.onTouchMove(event([[50, 400], [350, 400]]))
    const gesture = new Event('gesturechange', { cancelable: true })
    reader.onGesture(gesture)
    expect(reader.isGesturing.value).toBe(true)
    expect(onPinchStart).toHaveBeenCalled()
    expect(gesture.defaultPrevented).toBe(false)
    expect(listen).not.toHaveBeenCalled()
    expect(content.style.transform).toBe('')
    expect(content.style.getPropertyValue('--he-zoom')).toBe('1')
    expect(scroller.style.overflow).toBe('')
    reader.onTouchEnd(event([], 'touchend'))
    expect(reader.isGesturing.value).toBe(false)
    expect(reader.wasGesture()).toBe(true)
  })

  it('tracks document and visual viewport changes, then restores the original viewport and listeners', async () => {
    const { active, viewport, onScroll } = create()
    expect(document.documentElement.classList.contains('he-webtoon-document')).toBe(true)
    expect(document.querySelector('meta[name=viewport]')?.getAttribute('content')).toContain('maximum-scale=5')
    window.dispatchEvent(new Event('scroll')); viewport.dispatchEvent(new Event('scroll')); viewport.dispatchEvent(new Event('resize'))
    expect(onScroll).toHaveBeenCalledTimes(3)
    active.value = false; await nextTick()
    expect(document.documentElement.classList.contains('he-webtoon-document')).toBe(false)
    expect(document.querySelector('meta[name=viewport]')?.getAttribute('content')).toBe('width=device-width, initial-scale=1.0')
    window.dispatchEvent(new Event('scroll')); viewport.dispatchEvent(new Event('resize'))
    expect(onScroll).toHaveBeenCalledTimes(3)
  })

  it('resets zoom on exit and cancels a stale viewport restoration if the reader reopens immediately', async () => {
    const { active, viewport } = create()
    viewport.scale = 3
    active.value = false; await nextTick()
    expect(document.querySelector('meta[name=viewport]')?.getAttribute('content')).toContain('initial-scale=1.0001')
    active.value = true; await nextTick(); paint(); paint()
    expect(document.querySelector('meta[name=viewport]')?.getAttribute('content')).toContain('maximum-scale=5')
    active.value = false; await nextTick(); paint(); paint()
    expect(document.querySelector('meta[name=viewport]')?.getAttribute('content')).toBe('width=device-width, initial-scale=1.0')
  })

  it('cleans up when closed in the same tick as a mode change, before the post-render watcher runs', () => {
    const { active, onScroll, viewport } = create()
    active.value = false
    wrapper!.unmount(); wrapper = undefined
    window.dispatchEvent(new Event('scroll')); viewport.dispatchEvent(new Event('resize'))
    expect(onScroll).not.toHaveBeenCalled()
    expect(document.documentElement.classList.contains('he-webtoon-document')).toBe(false)
    expect(document.querySelector('meta[name=viewport]')?.getAttribute('content')).toBe('width=device-width, initial-scale=1.0')
  })
})
