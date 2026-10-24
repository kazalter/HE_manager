import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

export interface ReaderPagerOptions {
  pager: Ref<HTMLElement | null>
  currentSlot: () => number
  slotCount: () => number
  rtl: () => boolean
  /** A swipe came to rest on a different slot. */
  onSettle: (slot: number) => void
}

const SETTLE_MS = 120

/**
 * Native paging: a scroll-snap carousel of viewport-wide slots. The browser
 * moves the slots under the finger and decides where a swipe lands, as in a
 * photo gallery; this only maps scroll positions to slots and back.
 */
export function useReaderPager(options: ReaderPagerOptions) {
  const { pager } = options
  const width = ref(0)
  const height = ref(0)
  const visualSlot = ref(options.currentSlot())
  let frame: number | null = null
  let settleTimer: number | undefined
  let observer: ResizeObserver | undefined

  const lastSlot = () => Math.max(0, options.slotCount() - 1)
  // RTL pagers use direction: rtl, where scrollLeft runs from 0 towards negative values.
  const positionOf = (slot: number) => slot * width.value * (options.rtl() ? -1 : 1)
  const slotAt = (element: HTMLElement) => width.value
    ? Math.max(0, Math.min(lastSlot(), Math.round(Math.abs(element.scrollLeft) / width.value)))
    : options.currentSlot()

  const scrollToSlot = (slot: number) => {
    visualSlot.value = slot
    const element = pager.value
    if (!element || !width.value) return
    const target = positionOf(slot)
    if (Math.abs(element.scrollLeft - target) > 0.5) element.scrollLeft = target
  }

  const settle = () => {
    window.clearTimeout(settleTimer)
    settleTimer = undefined
    const element = pager.value
    if (!element || !width.value) return
    const slot = slotAt(element)
    visualSlot.value = slot
    // Only a swipe that came to rest on a slot counts; a paused finger does not.
    if (Math.abs(element.scrollLeft - positionOf(slot)) <= 1.5 && slot !== options.currentSlot()) options.onSettle(slot)
  }
  const onScroll = () => {
    if (frame === null) {
      frame = requestAnimationFrame(() => {
        frame = null
        if (pager.value) visualSlot.value = slotAt(pager.value)
      })
    }
    window.clearTimeout(settleTimer)
    settleTimer = window.setTimeout(settle, SETTLE_MS)
  }

  const measure = () => {
    const element = pager.value
    if (!element) return
    const resized = element.clientWidth !== width.value
    width.value = element.clientWidth
    height.value = element.clientHeight
    // Slots are percentages of the pager, so a resize must move the scroll position with them.
    if (resized) scrollToSlot(options.currentSlot())
  }
  watch(pager, (element, previous) => {
    observer?.disconnect()
    observer = undefined
    previous?.removeEventListener('scrollend', settle)
    if (!element) return
    element.addEventListener('scrollend', settle)
    measure()
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(measure)
      observer.observe(element)
    }
  }, { flush: 'post', immediate: true })

  // Programmatic navigation (keys, thumbnails, a loaded batch) jumps straight to its slot,
  // but never yanks a swipe that is still moving towards the same slot.
  watch([options.currentSlot, options.slotCount, options.rtl], ([slot], [previousSlot]) => {
    if (slot === previousSlot && settleTimer !== undefined) return
    scrollToSlot(slot)
  }, { flush: 'post' })

  onBeforeUnmount(() => {
    observer?.disconnect()
    pager.value?.removeEventListener('scrollend', settle)
    if (frame !== null) cancelAnimationFrame(frame)
    window.clearTimeout(settleTimer)
  })

  return { width, height, visualSlot, onScroll, scrollToSlot }
}
