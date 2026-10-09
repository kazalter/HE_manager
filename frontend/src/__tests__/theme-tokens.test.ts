import { afterEach, describe, expect, it } from 'vitest'
import { applyTheme, buildThemeTokens, namedThemeTokens, THEME_TOKENS, themes } from '../theme'

// Read from disk: Vitest stubs CSS imports, even with ?raw. Node modules are
// typed locally so the app tsconfig does not pull in @types/node globals.
declare const __dirname: string
const fsModule = 'node:fs'
const { readFileSync } = await import(/* @vite-ignore */ fsModule) as { readFileSync(path: string, encoding: 'utf8'): string }
const css = readFileSync(`${__dirname}/../style.css`, 'utf8')

const cssBlock = (themeId: string) => {
  const match = css.match(new RegExp(`:root\\[data-theme="${themeId}"\\]\\s*\\{([^}]*)\\}`))
  if (!match) throw new Error(`missing theme block ${themeId}`)
  return Object.fromEntries([...match[1]!.matchAll(/--color-([\w-]+):\s*([^;]+);/g)].map(m => [m[1], m[2]!.trim()]))
}

describe('theme tokens', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('style')
    delete document.documentElement.dataset.theme
  })

  it('keeps style.css palettes in sync with buildThemeTokens()', () => {
    for (const theme of themes) {
      expect(cssBlock(theme.id)).toEqual(namedThemeTokens(theme.id))
    }
  })

  it('never uses the invalid rgba(var(--token), a) form', () => {
    expect(css).not.toMatch(/rgba\(var\(/)
  })

  it('derives every token as an RGB triplet from a custom accent', () => {
    const tokens = buildThemeTokens('#ff6600')
    for (const key of THEME_TOKENS) expect(tokens[key]).toMatch(/^\d{1,3} \d{1,3} \d{1,3}$/)
    expect(tokens.accent).toBe('255 102 0')
  })

  it('applies a custom accent inline and clears it for a named theme', () => {
    applyTheme('#ff6600')
    const style = document.documentElement.style
    expect(document.documentElement.dataset.theme).toBe('custom')
    expect(style.getPropertyValue('--color-surface')).not.toBe('')
    expect(style.getPropertyValue('--color-on-accent')).not.toBe('')
    applyTheme('forest')
    expect(document.documentElement.dataset.theme).toBe('forest')
    for (const key of THEME_TOKENS) expect(style.getPropertyValue(`--color-${key}`)).toBe('')
    expect(localStorage.getItem('he-manager-theme')).toBe('forest')
  })
})
