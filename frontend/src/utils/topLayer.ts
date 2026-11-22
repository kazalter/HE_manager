let supportsDisplayTransition: boolean | undefined

function canTransitionDisplay(): boolean {
  if (supportsDisplayTransition !== undefined) return supportsDisplayTransition
  if (typeof window === 'undefined' || !window.CSS?.supports?.('transition-behavior', 'allow-discrete') || !document.body) {
    supportsDisplayTransition = false
    return false
  }
  const probe = document.createElement('div')
  probe.style.cssText = 'transition: display 1s allow-discrete !important; display: block;'
  document.body.appendChild(probe)
  getComputedStyle(probe).display
  probe.style.display = 'none'
  supportsDisplayTransition = getComputedStyle(probe).display === 'block'
  probe.remove()
  return supportsDisplayTransition
}

export function supportsTopLayerExit(): boolean {
  return typeof window !== 'undefined' && Boolean(window.CSS?.supports?.('overlay', 'auto')) && canTransitionDisplay()
}

/**
 * Closes a native `<dialog>` cleanly, running the CSS exit transition via
 * `[data-closing]` on browsers without `overlay` + discrete `display` transitions.
 * Resolves synchronously when no animations are active (e.g. reduced-motion or tests).
 */
export async function closeTopLayer(dialog: HTMLDialogElement | null | undefined, onFinish?: () => void): Promise<void> {
  if (!dialog) {
    onFinish?.()
    return
  }

  const reducedMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (!reducedMotion && !supportsTopLayerExit() && typeof dialog.getAnimations === 'function' && dialog.open) {
    dialog.setAttribute('data-closing', '')
    const animations = dialog.getAnimations({ subtree: true })
    if (animations.length > 0) {
      await Promise.race([
        Promise.allSettled(animations.map(a => a.finished)),
        new Promise<void>(resolve => window.setTimeout(resolve, 450)),
      ])
    }
    if (!dialog.hasAttribute('data-closing')) return
    dialog.removeAttribute('data-closing')
  }

  if (typeof dialog.close === 'function' && dialog.open) {
    try { dialog.close() } catch { dialog.removeAttribute('open') }
  } else {
    dialog.removeAttribute('open')
  }
  onFinish?.()
}
