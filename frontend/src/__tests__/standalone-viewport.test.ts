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
})
