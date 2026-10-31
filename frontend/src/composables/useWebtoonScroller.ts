import { computed, nextTick, ref, watch, type Ref } from 'vue'
import { useZoomScroller, type ZoomScrollerOptions } from './useZoomScroller'
import { useWebtoonDocument } from './useWebtoonDocument'

/** Shared continuous reader gestures for image sequences and manga chapters. */
export function useWebtoonScroller(options: Omit<ZoomScrollerOptions, 'centered' | 'boundedPinch'> & { native: Ref<boolean>; onScroll: () => void }) {
  const zoom = useZoomScroller({ ...options, boundedPinch: true, keyboard: () => !options.native.value && (options.keyboard?.() ?? true) })
  const pinching = ref(false)
  let lastTapAt = 0
  let doubleTap = false
  let active = false
  let startX = 0, startY = 0
  let scrolled = false
  const moved = (touch?: Touch) => !!touch && Math.hypot(touch.clientX - startX, touch.clientY - startY) > 8
  const onScroll = () => {
    if (active) scrolled = true
    options.onScroll()
  }
  watch(options.native, enabled => {
    active = false; pinching.value = false; scrolled = false; lastTapAt = 0; doubleTap = false
    if (enabled) zoom.reset()
  }, { flush: 'sync' })
  useWebtoonDocument(options.native, onScroll)
  return {
    ...zoom,
    isGesturing: computed(() => options.native.value ? pinching.value : zoom.isGesturing.value),
    onScroll,
    onTouchStart(event: TouchEvent) {
      if (!options.native.value) zoom.onTouchStart(event)
      if (!active) {
        scrolled = false
        startX = event.touches[0]?.clientX ?? 0
        startY = event.touches[0]?.clientY ?? 0
      }
      active = true
      if (event.touches.length !== 1) {
        scrolled = true; lastTapAt = 0
        if (options.native.value && !pinching.value) options.onPinchStart?.()
        pinching.value = true
      }
    },
    onTouchMove(event: TouchEvent) {
      if (!options.native.value) zoom.onTouchMove(event)
      if (event.touches.length !== 1 || moved(event.touches[0])) scrolled = true
    },
    onTouchEnd(event: TouchEvent) {
      if (!options.native.value) zoom.onTouchEnd(event)
      if (event.type === 'touchcancel' || moved(event.changedTouches[0])) scrolled = true
      if (options.native.value && !scrolled && !event.touches.length) {
        const now = performance.now()
        doubleTap = lastTapAt > 0 && now - lastTapAt < 350
        if (doubleTap) { scrolled = true; options.onDoubleTap?.() }
        lastTapAt = doubleTap ? 0 : now
      } else if (scrolled) lastTapAt = 0
      pinching.value = event.touches.length >= 2
      active = event.touches.length > 0
      if (!active) void nextTick(options.onScroll)
    },
    onGesture(event: Event) {
      if (!options.native.value) zoom.onGesture(event)
      else { scrolled = true; options.onPinchStart?.() }
    },
    onMouseDown(event: MouseEvent) { if (!options.native.value) zoom.onMouseDown(event) },
    wasDoubleTap() {
      if (!options.native.value) return zoom.wasDoubleTap()
      const handled = doubleTap; doubleTap = false
      return handled
    },
    wasGesture() {
      const suppress = zoom.wasGesture() || scrolled
      scrolled = false
      return suppress
    },
  }
}
