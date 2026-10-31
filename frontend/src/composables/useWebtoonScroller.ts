import { computed, watch, type Ref } from 'vue'
import { useZoomScroller, type ZoomScrollerOptions } from './useZoomScroller'
import { useWebtoonDocument } from './useWebtoonDocument'

/** Mobile uses the browser's reader document; desktop keeps mouse/keyboard zoom. */
export function useWebtoonScroller(options: Omit<ZoomScrollerOptions, 'centered' | 'boundedPinch'> & { native: Ref<boolean>; onScroll: () => void }) {
  const zoom = useZoomScroller({ ...options, boundedPinch: true, keyboard: () => !options.native.value && (options.keyboard?.() ?? true) })
  let lastScale = 1, active = false, scrolled = false, startX = 0, startY = 0
  const moved = (touch?: Touch) => !!touch && Math.hypot(touch.clientX - startX, touch.clientY - startY) > 8
  const onScroll = () => {
    if (active) scrolled = true
    const scale = window.visualViewport?.scale ?? 1
    if (options.native.value && scale > 1.01 && lastScale <= 1.01) options.onPinchStart?.()
    lastScale = scale
    options.onScroll()
  }
  watch(options.native, enabled => { lastScale = 1; active = false; scrolled = false; if (enabled) zoom.reset() }, { flush: 'sync' })
  useWebtoonDocument(options.native, onScroll)
  return {
    ...zoom,
    isGesturing: computed(() => !options.native.value && zoom.isGesturing.value),
    onScroll,
    onTouchStart(event: TouchEvent) {
      if (options.native.value) return
      if (!active) { scrolled = false; startX = event.touches[0]?.clientX ?? 0; startY = event.touches[0]?.clientY ?? 0 }
      active = true
      if (event.touches.length !== 1) scrolled = true
      zoom.onTouchStart(event)
    },
    onTouchMove(event: TouchEvent) {
      if (options.native.value) return
      if (event.touches.length !== 1 || moved(event.touches[0])) scrolled = true
      zoom.onTouchMove(event)
    },
    onTouchEnd(event: TouchEvent) {
      if (options.native.value) return
      if (event.type === 'touchcancel' || moved(event.changedTouches[0])) scrolled = true
      active = event.touches.length > 0
      zoom.onTouchEnd(event)
    },
    onGesture(event: Event) { if (!options.native.value) zoom.onGesture(event) },
    onMouseDown(event: MouseEvent) { if (!options.native.value) zoom.onMouseDown(event) },
    wasDoubleTap: () => !options.native.value && zoom.wasDoubleTap(),
    wasGesture() {
      if (options.native.value) return false
      const suppress = zoom.wasGesture() || scrolled; scrolled = false; return suppress
    },
  }
}
