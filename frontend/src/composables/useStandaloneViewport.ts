import { onMounted, onBeforeUnmount } from 'vue'

// Installed iOS web apps can report dvh/visualViewport without the safe areas.
// Keep the full CSS vh height normally; use visualViewport only for the keyboard.
export function useStandaloneViewport() {
  const displayMode = window.matchMedia('(display-mode: standalone)')
  const viewport = window.visualViewport
  const html = document.documentElement
  let probe: HTMLDivElement | null = null
  let frame = 0

  const update = () => {
    frame = 0
    const standalone = displayMode.matches || (navigator as Navigator & { standalone?: boolean }).standalone === true
    html.classList.toggle('he-standalone', standalone)
    if (!standalone) {
      html.classList.remove('he-keyboard-open')
      html.style.removeProperty('--he-app-height')
      probe?.remove(); probe = null
      return
    }
    if (!probe) {
      probe = document.createElement('div')
      probe.setAttribute('aria-hidden', 'true')
      probe.style.cssText = 'position:absolute;width:0;height:100vh;top:0;left:0;visibility:hidden;pointer-events:none;'
      document.body.appendChild(probe)
    }
    const focused = document.activeElement
    const editable = focused instanceof HTMLElement && (
      focused.isContentEditable || focused.tagName === 'TEXTAREA' ||
      (focused instanceof HTMLInputElement && !['button', 'submit', 'reset', 'checkbox', 'radio', 'range', 'color', 'file', 'hidden'].includes(focused.type))
    )
    const fullHeight = probe.getBoundingClientRect().height
    const visibleBottom = viewport ? viewport.height + viewport.offsetTop : fullHeight
    // A small safe-area mismatch is not a keyboard; pinch zoom is not one either.
    const keyboard = editable && !!viewport && Math.abs(viewport.scale - 1) < 0.02 && fullHeight - visibleBottom > 150
    html.classList.toggle('he-keyboard-open', keyboard)
    if (keyboard) html.style.setProperty('--he-app-height', `${Math.round(visibleBottom)}px`)
    else html.style.removeProperty('--he-app-height')
  }
  const schedule = () => { if (!frame) frame = window.requestAnimationFrame(update) }
  onMounted(() => {
    update()
    displayMode.addEventListener('change', schedule)
    window.addEventListener('resize', schedule, { passive: true })
    window.addEventListener('pageshow', schedule)
    document.addEventListener('visibilitychange', schedule)
    document.addEventListener('focusin', schedule)
    document.addEventListener('focusout', schedule)
    viewport?.addEventListener('resize', schedule, { passive: true })
    viewport?.addEventListener('scroll', schedule, { passive: true })
  })
  onBeforeUnmount(() => {
    window.cancelAnimationFrame(frame)
    displayMode.removeEventListener('change', schedule)
    window.removeEventListener('resize', schedule)
    window.removeEventListener('pageshow', schedule)
    document.removeEventListener('visibilitychange', schedule)
    document.removeEventListener('focusin', schedule)
    document.removeEventListener('focusout', schedule)
    viewport?.removeEventListener('resize', schedule)
    viewport?.removeEventListener('scroll', schedule)
    probe?.remove()
    html.classList.remove('he-standalone', 'he-keyboard-open')
    html.style.removeProperty('--he-app-height')
  })
}
