// Coordinates are viewport CSS pixels, matching native pointer events.
// Wallpaper windows cannot receive focus, so input arrives via the desktop bridge.
export function routeWallpaperPointer(gestures, view, pointer, rippleCtl = null) {
  if (!view || !pointer || !Number.isFinite(pointer.x) || !Number.isFinite(pointer.y)) return
  const event = { clientX: pointer.x, clientY: pointer.y, target: view, pointerId: 1 }
  if (pointer.type === 'down') {
    rippleCtl?.onPointerDown?.(event)
    gestures.onPointerDown(event)
  } else if (pointer.type === 'move') {
    rippleCtl?.onPointerMove?.(event)
    gestures.onPointerMove(event)
  } else if (pointer.type === 'up') {
    rippleCtl?.onPointerUp?.()
    gestures.onPointerUp(event)
  } else if (pointer.type === 'cancel') {
    rippleCtl?.onPointerUp?.()
    gestures.onPointerCancel()
  }
}
