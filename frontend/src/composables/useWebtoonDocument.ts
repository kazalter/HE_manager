import { onBeforeUnmount, watch, type Ref } from 'vue'

/** Mobile long-strip reading uses the document's scroll/zoom, as a normal web page. */
export function useWebtoonDocument(active: Ref<boolean>, onScroll: () => void) {
  let savedX = 0, savedY = 0
  let releaseViewport: (() => void) | null = null
  let restoreFrame = 0
  let attached = false
  const viewport = window.visualViewport
  const stop = () => {
    if (!attached) return
    attached = false
    window.removeEventListener('scroll', onScroll)
    viewport?.removeEventListener('scroll', onScroll)
    viewport?.removeEventListener('resize', onScroll)
    document.documentElement.classList.remove('he-webtoon-document')
    window.scrollTo(savedX, savedY)
    if (!releaseViewport) return
    if ((viewport?.scale ?? 1) > 1.01) {
      // Do not leave the library magnified when closing or changing reading mode.
      // Change initial-scale too: changing maximum alone does not reset Chromium.
      document.querySelector('meta[name="viewport"]')?.setAttribute('content',
        'width=device-width, initial-scale=1.0001, minimum-scale=1, maximum-scale=1.0001')
      restoreFrame = requestAnimationFrame(() => {
        restoreFrame = requestAnimationFrame(() => { restoreFrame = 0; releaseViewport?.(); releaseViewport = null })
      })
    } else { releaseViewport(); releaseViewport = null }
  }
  watch(active, enabled => {
    if (!enabled) { stop(); return }
    if (restoreFrame) { cancelAnimationFrame(restoreFrame); restoreFrame = 0 }
    releaseViewport?.()
    savedX = window.scrollX; savedY = window.scrollY
    const existing = document.querySelector<HTMLMetaElement>('meta[name="viewport"]')
    const meta = existing ?? document.createElement('meta')
    const original = meta.getAttribute('content')
    if (!existing) { meta.name = 'viewport'; document.head.append(meta) }
    releaseViewport = () => {
      if (!existing) meta.remove()
      else if (original === null) meta.removeAttribute('content')
      else meta.content = original
    }
    meta.content = 'width=device-width, initial-scale=1, minimum-scale=1, maximum-scale=5, user-scalable=yes'
    document.documentElement.classList.add('he-webtoon-document')
    attached = true
    window.addEventListener('scroll', onScroll, { passive: true })
    viewport?.addEventListener('scroll', onScroll, { passive: true })
    viewport?.addEventListener('resize', onScroll, { passive: true })
  }, { immediate: true, flush: 'post' })
  onBeforeUnmount(stop)
}
