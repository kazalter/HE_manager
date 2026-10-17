import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { applyColorMode, applyTheme, buildThemeTokens, initTheme, themeState, themes, toggleColorMode } from '../theme'
import ColorModeToggle from '../components/ColorModeToggle.vue'
import ColorModeSelect from '../components/ColorModeSelect.vue'

const luminance = (value: string) => value.split(' ').map(Number).reduce((sum, channel, i) => {
  const c = channel / 255
  return sum + (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4) * [0.2126, 0.7152, 0.0722][i]!
}, 0)
const contrast = (a: string, b: string) => {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (values[0]! + 0.05) / (values[1]! + 0.05)
}

afterEach(() => {
  vi.restoreAllMocks()
  applyColorMode('dark')
  applyTheme('midnight')
  localStorage.clear()
  document.head.innerHTML = ''
})

describe('color modes', () => {
  it('restores mode and accent together on startup and preserves accents when toggling', () => {
    localStorage.setItem('he-manager-color-mode', 'light')
    localStorage.setItem('he-manager-theme', 'forest')
    document.head.innerHTML = '<meta name="theme-color"><meta name="color-scheme">'
    initTheme()
    expect(themeState.resolvedMode).toBe('light')
    expect(document.documentElement.dataset.colorMode).toBe('light')
    expect(document.querySelector('meta[name="color-scheme"]')?.getAttribute('content')).toBe('light')
    const lightBackground = document.documentElement.style.getPropertyValue('--color-background')
    expect(lightBackground).not.toBe('')
    toggleColorMode()
    expect(themeState.resolvedMode).toBe('dark')
    expect(themeState.theme).toBe('forest')
    expect(localStorage.getItem('he-manager-color-mode')).toBe('dark')
    expect(document.documentElement.style.getPropertyValue('--color-background')).toBe('')
    toggleColorMode()
    expect(document.documentElement.style.getPropertyValue('--color-background')).toBe(lightBackground)
  })

  it('keeps text and all accent choices readable in light mode', () => {
    for (const accent of ['#6366f1', '#f27aba', '#3ccf97', '#f2a33a', '#ffffff', '#ffff00', '#000000']) {
      const tokens = buildThemeTokens(accent, 'light')
      for (const surface of [tokens.background, tokens.surface, tokens['surface-2'], tokens['surface-3']]) {
        for (const text of [tokens.ink, tokens.muted, tokens.subtle, tokens.accent]) expect(contrast(text, surface)).toBeGreaterThanOrEqual(4.5)
      }
      expect(contrast(tokens['on-accent'], tokens.accent)).toBeGreaterThanOrEqual(4.5)
    }
    for (const theme of themes) {
      applyTheme(theme.id)
      applyColorMode('light')
      expect(themeState.theme).toBe(theme.id)
      applyColorMode('dark')
    }
  })

  it('tracks OS changes only while following the system', async () => {
    vi.resetModules()
    const query = new EventTarget()
    let dark = false
    Object.defineProperty(query, 'matches', { get: () => dark })
    vi.spyOn(window, 'matchMedia').mockReturnValue(query as MediaQueryList)
    const isolated = await import('../theme')
    isolated.initTheme()
    isolated.applyColorMode('system')
    expect(isolated.themeState.resolvedMode).toBe('light')
    dark = true
    query.dispatchEvent(new Event('change'))
    expect(isolated.themeState.resolvedMode).toBe('dark')
    isolated.applyColorMode('light')
    dark = false
    query.dispatchEvent(new Event('change'))
    dark = true
    query.dispatchEvent(new Event('change'))
    expect(isolated.themeState.resolvedMode).toBe('light')
  })

  it('synchronizes another tab and handles cleared or invalid preferences', () => {
    initTheme()
    localStorage.setItem('he-manager-color-mode', 'light')
    localStorage.setItem('he-manager-theme', '#ff6600')
    window.dispatchEvent(new StorageEvent('storage', { key: 'he-manager-color-mode' }))
    expect(themeState.resolvedMode).toBe('light')
    expect(themeState.theme).toBe('#ff6600')
    localStorage.clear()
    window.dispatchEvent(new StorageEvent('storage', { key: null }))
    expect(themeState.mode).toBe('dark')
    expect(themeState.theme).toBe('midnight')
    localStorage.setItem('he-manager-theme', 'invalid')
    initTheme()
    expect(themeState.theme).toBe('midnight')
  })

  it('remains usable when browser storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(() => applyColorMode('light')).not.toThrow()
    expect(themeState.resolvedMode).toBe('light')
  })

  it('updates every mounted control immediately when a mode is selected', async () => {
    const toggle = mount(ColorModeToggle)
    const select = mount(ColorModeSelect)
    await select.get('button').trigger('click')
    expect(toggle.get('button').attributes('aria-label')).toBe('切换到黑夜模式')
    expect(select.get('button').attributes('aria-pressed')).toBe('true')
    await toggle.get('button').trigger('click')
    expect(select.findAll('button')[1]!.attributes('aria-pressed')).toBe('true')
    toggle.unmount()
    select.unmount()
  })
})
