import { nextTick } from 'vue'
import { useZoomScroller, type ZoomScrollerOptions } from './useZoomScroller'

/** Shared continuous reader gestures for image sequences and manga chapters. */
export function useWebtoonScroller(options: Omit<ZoomScrollerOptions, 'centered' | 'boundedPinch'> & { onScroll: () => void }) {
  const zoom = useZoomScroller({ ...options, boundedPinch: true })
  let active = false
  let startX = 0, startY = 0
  let scrolled = false
  const moved = (touch?: Touch) => !!touch && Math.hypot(touch.clientX - startX, touch.clientY - startY) > 8
  const onScroll = () => {
    if (active) scrolled = true
    options.onScroll()
  }
  return {
    ...zoom,
    onScroll,
    onTouchStart(event: TouchEvent) {
      zoom.onTouchStart(event)
      if (!active) {
        scrolled = false
        startX = event.touches[0]?.clientX ?? 0
        startY = event.touches[0]?.clientY ?? 0
      }
      active = true
      if (event.touches.length !== 1) scrolled = true
    },
    onTouchMove(event: TouchEvent) {
      zoom.onTouchMove(event)
      if (event.touches.length !== 1 || moved(event.touches[0])) scrolled = true
    },
    onTouchEnd(event: TouchEvent) {
      zoom.onTouchEnd(event)
      if (event.type === 'touchcancel' || moved(event.changedTouches[0])) scrolled = true
      active = event.touches.length > 0
      if (!active) void nextTick(options.onScroll)
    },
    wasGesture() {
      const suppress = zoom.wasGesture() || scrolled
      scrolled = false
      return suppress
    },
  }
}
