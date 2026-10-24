import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useReaderPager } from '../composables/useReaderPager'

let wrapper: ReturnType<typeof mount> | undefined
beforeEach(() => { vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers(); vi.restoreAllMocks() })

async function create(options: { slots?: number; current?: number; rtl?: boolean } = {}) {
  const element = document.createElement('div')
  let width = 400
  Object.defineProperties(element, { clientWidth: { get: () => width }, clientHeight: { get: () => 800 } })
  const current = ref(options.current ?? 0), count = ref(options.slots ?? 5), rtl = ref(options.rtl ?? false)
  const onSettle = vi.fn((slot: number) => { current.value = slot })
  let pager!: ReturnType<typeof useReaderPager>
  wrapper = mount(defineComponent({
    setup() {
      pager = useReaderPager({ pager: ref(element), currentSlot: () => current.value, slotCount: () => count.value, rtl: () => rtl.value, onSettle })
      return () => h('div')
    },
  }))
  await nextTick()
  const swipeTo = (left: number) => { element.scrollLeft = left; pager.onScroll() }
  return { element, pager, current, count, rtl, onSettle, swipeTo, resize: (next: number) => { width = next } }
}

it('reports a swipe once it rests on another slot', async () => {
  const { pager, onSettle, swipeTo, current } = await create()
  swipeTo(150); swipeTo(320); swipeTo(400)
  expect(onSettle).not.toHaveBeenCalled()
  vi.advanceTimersByTime(150)
  expect(onSettle).toHaveBeenCalledExactlyOnceWith(1)
  expect(current.value).toBe(1)
  expect(pager.visualSlot.value).toBe(1)
})

it('settles immediately on scrollend, and ignores a finger paused between slots', async () => {
  const { element, onSettle, swipeTo } = await create()
  swipeTo(230)
  vi.advanceTimersByTime(150)
  expect(onSettle).not.toHaveBeenCalled()
  swipeTo(800)
  element.dispatchEvent(new Event('scrollend'))
  expect(onSettle).toHaveBeenCalledExactlyOnceWith(2)
})

it('maps right-to-left scroll positions, which run negative', async () => {
  const { element, onSettle, swipeTo, current } = await create({ rtl: true })
  swipeTo(-400)
  vi.advanceTimersByTime(150)
  expect(onSettle).toHaveBeenCalledExactlyOnceWith(1)
  current.value = 3; await nextTick()
  expect(element.scrollLeft).toBe(-1200)
})

it('jumps to a slot chosen elsewhere, and keeps it under a resize', async () => {
  const observers: Array<() => void> = []
  vi.stubGlobal('ResizeObserver', class { constructor(callback: () => void) { observers.push(callback) } observe() {} disconnect() {} })
  const { element, current, resize, pager } = await create()
  current.value = 3; await nextTick()
  expect(element.scrollLeft).toBe(1200)
  resize(500)
  observers.forEach(callback => callback())
  expect(pager.width.value).toBe(500)
  expect(element.scrollLeft).toBe(1500)
  vi.unstubAllGlobals()
})

it('does not yank a moving swipe when the slot count changes', async () => {
  const { element, count, swipeTo, onSettle } = await create()
  swipeTo(260)
  count.value = 6; await nextTick()
  expect(element.scrollLeft).toBe(260)
  swipeTo(400)
  vi.advanceTimersByTime(150)
  expect(onSettle).toHaveBeenCalledExactlyOnceWith(1)
})
