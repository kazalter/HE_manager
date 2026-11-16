import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { useStandaloneViewport } from '../composables/useStandaloneViewport'

let wrapper: ReturnType<typeof mount> | undefined
const start = (standalone: boolean) => {
  vi.useFakeTimers()
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => window.setTimeout(() => callback(0), 0))
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(id => window.clearTimeout(id))
  const display = Object.assign(new EventTarget(), { matches: standalone })
  const viewport = Object.assign(new EventTarget(), { height: 780, offsetTop: 0, scale: 1 })
  vi.spyOn(window, 'matchMedia').mockReturnValue(display as unknown as MediaQueryList)
  vi.stubGlobal('visualViewport', viewport)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ height: 844 } as DOMRect)
  wrapper = mount({ setup() { useStandaloneViewport(); return {} }, template: '<input aria-label="搜索" />' }, { attachTo: document.body })
  return viewport
}
afterEach(() => {
  wrapper?.unmount(); wrapper = undefined
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers()
})

describe('installed app viewport', () => {
  it('keeps full CSS viewport height when iOS reports smaller visualViewport safe areas', () => {
    start(true)
    const probe = document.body.querySelector('div[aria-hidden="true"]') as HTMLElement | null
    expect(probe?.style.position).toBe('fixed')
    expect(probe?.style.top).toBe('0px')
    expect(probe?.style.bottom).toBe('0px')
    expect(document.documentElement.classList.contains('he-standalone')).toBe(true)
    expect(document.documentElement.style.getPropertyValue('--he-app-height')).toBe('')
    expect(document.documentElement.classList.contains('he-keyboard-open')).toBe(false)
  })
  it('resizes for an actual keyboard and restores full height after it closes', () => {
    const viewport = start(true)
    wrapper!.get('input').element.focus()
    viewport.height = 460
    viewport.dispatchEvent(new Event('resize'))
    vi.runAllTimers()
    expect(document.documentElement.style.getPropertyValue('--he-app-height')).toBe('460px')
    expect(document.documentElement.classList.contains('he-keyboard-open')).toBe(true)
    viewport.height = 780
    viewport.dispatchEvent(new Event('resize'))
    vi.runAllTimers()
    expect(document.documentElement.style.getPropertyValue('--he-app-height')).toBe('')
    expect(document.documentElement.classList.contains('he-keyboard-open')).toBe(false)
  })
  it('does not treat pinch zoom as a keyboard or change regular browser mode', () => {
    const viewport = start(true)
    wrapper!.get('input').element.focus()
    viewport.height = 420; viewport.scale = 2
    viewport.dispatchEvent(new Event('resize'))
    vi.runAllTimers()
    expect(document.documentElement.style.getPropertyValue('--he-app-height')).toBe('')
    wrapper!.unmount(); wrapper = undefined
    expect(document.documentElement.classList.contains('he-standalone')).toBe(false)
    start(false)
    expect(document.documentElement.classList.contains('he-standalone')).toBe(false)
    expect(document.documentElement.style.getPropertyValue('--he-app-height')).toBe('')
  })

  it('keeps fixed media viewers anchored by inset:0 without forcing 100vh/100% height and exposes standard safe-bottom', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const root = path.resolve(__dirname, '../..')
    const indexHtml = fs.readFileSync(path.join(root, 'index.html'), 'utf8')
    const styleCss = fs.readFileSync(path.join(root, 'src/style.css'), 'utf8')
    const mediaDetail = fs.readFileSync(path.join(root, 'src/components/MediaDetail.vue'), 'utf8')
    const pawchiveViewer = fs.readFileSync(path.join(root, 'src/components/external/pawchive/PawchiveMediaViewer.vue'), 'utf8')
    const mangaReader = fs.readFileSync(path.join(root, 'src/components/media-detail/MangaReader.vue'), 'utf8')
    const nativePages = fs.readFileSync(path.join(root, 'src/components/media-detail/NativeWebtoonPages.vue'), 'utf8')

    expect(indexHtml).toContain('--he-safe-bottom: 34px;')
    expect(styleCss).toContain('--he-safe-bottom: env(safe-area-inset-bottom, 0px);')
    expect(styleCss).toContain('html.he-standalone.he-webtoon-document body')
    expect(mediaDetail).toContain('.he-media-overlay { padding-left:')
    expect(mediaDetail).not.toContain('100dvh')
    expect(mediaDetail).toContain(':global(html.he-keyboard-open) .he-media-overlay { height: var(--he-app-height); }')
    expect(pawchiveViewer).not.toContain('var(--he-app-height, 100dvh)')
    expect(pawchiveViewer).not.toContain('100dvh')
    expect(pawchiveViewer).toContain(':global(html.he-keyboard-open) .he-pawchive-viewer { height: var(--he-app-height); }')
    expect(pawchiveViewer).toContain('var(--he-safe-bottom')
    expect(mangaReader).toContain('var(--he-safe-bottom')
    expect(nativePages).toContain('html.he-standalone .he-native-pages { min-height: 0; }')
  })
})
