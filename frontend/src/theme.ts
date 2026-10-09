export type ThemeId = 'midnight' | 'sakura' | 'forest' | 'amber' | string

export interface ThemeOption {
  id: ThemeId
  name: string
  description: string
  /** Hex colors for previews: [background, surface, accent]. */
  swatches: string[]
}

const STORAGE_KEY = 'he-manager-theme'
const DEFAULT_THEME: ThemeId = 'midnight'

/**
 * Every color token a theme defines. Each one is a space-separated RGB triplet
 * ("12 12 16") exposed as `--color-<token>` and as the Tailwind color `<token>`,
 * so `bg-surface/80` and `rgb(var(--color-surface) / 0.8)` both work.
 */
export const THEME_TOKENS = [
  'background',
  'sidebar',
  'surface',
  'surface-2',
  'surface-3',
  'line',
  'line-strong',
  'ink',
  'muted',
  'subtle',
  'faint',
  'accent',
  'accent-glow',
  'on-accent',
] as const

export type ThemeToken = typeof THEME_TOKENS[number]
export type ThemeTokens = Record<ThemeToken, string>

/** Accent colors of the named themes. All other tokens derive from these. */
const THEME_ACCENTS: Record<string, string> = {
  midnight: '#6366f1',
  sakura: '#f27aba',
  forest: '#3ccf97',
  amber: '#f2a33a',
}

const hexToRgb = (hex: string): number[] => {
  let c = hex.substring(1)
  if (c.length === 3) c = c.split('').map(char => char + char).join('')
  const num = parseInt(c, 16)
  return [num >> 16, (num >> 8) & 255, num & 255]
}

const rgbToHex = (rgb: number[]) => '#' + rgb.map(value => value.toString(16).padStart(2, '0')).join('')

const rgbToHsl = (r: number, g: number, b: number) => {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  let h = 0, s = 0, l = (max + min) / 2
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break
      case g: h = (b - r) / d + 2; break
      case b: h = (r - g) / d + 4; break
    }
    h /= 6
  }
  return [h, s, l]
}

const hslToRgb = (h: number, s: number, l: number) => {
  let r, g, b
  if (s === 0) {
    r = g = b = l
  } else {
    const hue2rgb = (p: number, q: number, t: number) => {
      if (t < 0) t += 1
      if (t > 1) t -= 1
      if (t < 1/6) return p + (q - p) * 6 * t
      if (t < 1/2) return q
      if (t < 2/3) return p + (q - p) * (2/3 - t) * 6
      return p
    }
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s
    const p = 2 * l - q
    r = hue2rgb(p, q, h + 1/3)
    g = hue2rgb(p, q, h)
    b = hue2rgb(p, q, h - 1/3)
  }
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)]
}

const luminance = (rgb: number[]) => {
  const [r = 0, g = 0, b = 0] = rgb.map(value => {
    const v = value / 255
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

const contrast = (a: number[], b: number[]) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi! + 0.05) / (lo! + 0.05)
}

/**
 * Builds the full dark palette from one accent color: hue-tinted neutral
 * surfaces (background → surface-3), hairlines, four text levels and the
 * accent with its readable on-accent text color.
 */
export const buildThemeTokens = (accentHex: string): ThemeTokens => {
  const accent = hexToRgb(accentHex)
  const [h, s, l] = rgbToHsl(accent[0]!, accent[1]!, accent[2]!)
  const ns = Math.min(0.12, s)
  const ts = Math.min(0.08, s)
  const neutral = (lightness: number, saturation = ns) => hslToRgb(h, saturation, lightness)
  const white = [255, 255, 255]
  const onAccent = contrast(white, accent) >= 4.2 ? white : hslToRgb(h, Math.min(0.3, s), 0.07)
  const glow = hslToRgb(h, Math.min(1, s + 0.1), Math.min(0.88, Math.max(l + 0.2, 0.78)))
  const tokens: Record<ThemeToken, number[]> = {
    background: neutral(0.045),
    sidebar: neutral(0.062),
    surface: neutral(0.078),
    'surface-2': neutral(0.11),
    'surface-3': neutral(0.14),
    line: neutral(0.165),
    'line-strong': neutral(0.235),
    ink: neutral(0.95, ts),
    muted: neutral(0.72, ts),
    subtle: neutral(0.57, ts * 0.9),
    faint: neutral(0.4, ts * 0.8),
    accent,
    'accent-glow': glow,
    'on-accent': onAccent,
  }
  return Object.fromEntries(Object.entries(tokens).map(([key, rgb]) => [key, rgb.join(' ')])) as ThemeTokens
}

const tokenHex = (tokens: ThemeTokens, key: ThemeToken) => rgbToHex(tokens[key].split(' ').map(Number))

const option = (id: string, name: string, description: string): ThemeOption => {
  const tokens = buildThemeTokens(THEME_ACCENTS[id]!)
  return { id, name, description, swatches: [tokenHex(tokens, 'background'), tokenHex(tokens, 'surface-2'), tokenHex(tokens, 'accent')] }
}

export const themes: ThemeOption[] = [
  option('midnight', '午夜蓝', '冷静、克制，适合长时间整理媒体库。'),
  option('sakura', '樱花粉', '更柔和一点，适合图片和漫画浏览。'),
  option('forest', '深林绿', '低刺激、高辨识，筛选和整理时很舒服。'),
  option('amber', '琥珀色', '偏暖的夜间主题，视觉上更有收藏室感。'),
]

/** Token values of a named theme (the same values style.css hard-codes). */
export const namedThemeTokens = (themeId: string): ThemeTokens | null =>
  THEME_ACCENTS[themeId] ? buildThemeTokens(THEME_ACCENTS[themeId]!) : null

export const isThemeId = (value: string | null): boolean => {
  if (!value) return false
  if (value.startsWith('#') && /^#[0-9A-Fa-f]{6}$/i.test(value)) return true
  return themes.some(theme => theme.id === value)
}

export const getStoredTheme = (): string => {
  if (typeof window === 'undefined') return DEFAULT_THEME
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return isThemeId(stored) ? stored! : DEFAULT_THEME
}

const syncThemeColorMeta = (tokens: ThemeTokens | null) => {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  if (meta && tokens) meta.content = tokenHex(tokens, 'background')
}

export const applyTheme = (themeId: string) => {
  window.localStorage.setItem(STORAGE_KEY, themeId)
  const root = document.documentElement

  if (themeId.startsWith('#')) {
    root.dataset.theme = 'custom'
    const tokens = buildThemeTokens(themeId)
    for (const key of THEME_TOKENS) root.style.setProperty(`--color-${key}`, tokens[key])
    syncThemeColorMeta(tokens)
  } else {
    root.dataset.theme = themeId
    for (const key of THEME_TOKENS) root.style.removeProperty(`--color-${key}`)
    syncThemeColorMeta(namedThemeTokens(themeId))
  }
}

export const initTheme = () => {
  applyTheme(getStoredTheme())
}
