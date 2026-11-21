import { reactive, readonly } from 'vue'

export type VisualDensity = 'spacious' | 'comfortable' | 'compact'

export interface DensityOption {
  id: VisualDensity
  label: string
  shortLabel: string
  description: string
}

const STORAGE_KEY = 'he_visual_density'
const DEFAULT_DENSITY: VisualDensity = 'comfortable'

export const DENSITY_OPTIONS: DensityOption[] = [
  {
    id: 'spacious',
    label: '宽松画廊',
    shortLabel: '宽松',
    description: '更大封面与充裕留白，减少视线干扰，适合沉浸赏图',
  },
  {
    id: 'comfortable',
    label: '舒适默认',
    shortLabel: '舒适',
    description: '黄金比例与柔和节奏，适合日常浏览与长期阅读',
  },
  {
    id: 'compact',
    label: '紧凑浏览',
    shortLabel: '紧凑',
    description: '更高信息密度与精简间距，一屏快速总览更多作品',
  },
]

const isDensity = (value: unknown): value is VisualDensity =>
  value === 'spacious' || value === 'comfortable' || value === 'compact'

const state = reactive<{ density: VisualDensity }>({
  density: DEFAULT_DENSITY,
})

export const densityState = readonly(state)

const renderDensity = (next: VisualDensity) => {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.dataset.density = next
  root.style.setProperty('--density', next)
}

export const applyDensity = (density: VisualDensity | string) => {
  const next: VisualDensity = isDensity(density) ? density : DEFAULT_DENSITY
  state.density = next
  try {
    window.localStorage.setItem(STORAGE_KEY, next)
  } catch {
    /* Layout density works cleanly even when storage is unavailable. */
  }
  renderDensity(next)
}

export const cycleDensity = () => {
  const order: VisualDensity[] = ['comfortable', 'spacious', 'compact']
  const index = order.indexOf(state.density)
  const next = order[(index + 1) % order.length]!
  applyDensity(next)
}

export const initDensity = () => {
  let stored: string | null = null
  try {
    stored = window.localStorage.getItem(STORAGE_KEY)
  } catch {
    stored = null
  }
  const next: VisualDensity = isDensity(stored) ? stored : DEFAULT_DENSITY
  state.density = next
  renderDensity(next)
}
