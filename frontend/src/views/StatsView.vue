<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import axios from 'axios'
import {
  ArrowUpRight,
  BarChart3,
  Clock,
  Eye,
  Film,
  Flame,
  HardDrive,
  Image as ImageIcon,
  Layers,
  Music,
  PieChart,
  RefreshCw,
  Sparkles,
  Star,
  TrendingUp,
} from 'lucide-vue-next'
import { API_BASE_URL, thumbnailUrl } from '../config'
import type {
  StatAttentionItem,
  StatsActivity,
  StatsActivityBucket,
  StatsAttention,
  StatsDistribution,
  StatsHighlights,
  StatsOverview,
} from '../types'

const loading = ref(true)
const errorMessage = ref('')
const refreshSpinning = ref(false)
const lastUpdatedTime = ref('')

const overview = ref<StatsOverview | null>(null)
const distribution = ref<StatsDistribution | null>(null)
const activity = ref<StatsActivity | null>(null)
const attention = ref<StatsAttention | null>(null)
const highlights = ref<StatsHighlights | null>(null)

const activeSection = ref('section-overview')
let isManualScrolling = false
let scrollTimeout: number | undefined

const navSections = [
  { id: 'section-overview', label: '概览指标', icon: BarChart3 },
  { id: 'section-distribution', label: '资产分布', icon: PieChart },
  { id: 'section-growth', label: '入库趋势', icon: TrendingUp },
  { id: 'section-activity', label: '活跃轨迹', icon: Flame },
  { id: 'section-attention', label: '整理与亮点', icon: Sparkles },
]

const scrollToSection = (id: string) => {
  activeSection.value = id
  isManualScrolling = true
  if (scrollTimeout) clearTimeout(scrollTimeout)
  scrollTimeout = window.setTimeout(() => {
    isManualScrolling = false
  }, 800)

  const target = document.getElementById(id)
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

let observer: IntersectionObserver | null = null

const initObserver = () => {
  if (typeof IntersectionObserver === 'undefined') return
  observer?.disconnect()

  const ids = ['section-overview', 'section-distribution', 'section-growth', 'section-activity', 'section-attention']
  observer = new IntersectionObserver(
    (entries) => {
      if (isManualScrolling) return
      const visible = entries.filter((e) => e.isIntersecting)
      if (visible.length > 0) {
        visible.sort((a, b) => Math.abs(a.boundingClientRect.top) - Math.abs(b.boundingClientRect.top))
        if (visible[0]?.target?.id) {
          activeSection.value = visible[0].target.id
        }
      }
    },
    {
      rootMargin: '-15% 0px -60% 0px',
      threshold: [0, 0.2, 0.5],
    },
  )

  ids.forEach((id) => {
    const el = document.getElementById(id)
    if (el) observer?.observe(el)
  })
}

onBeforeUnmount(() => {
  observer?.disconnect()
  if (scrollTimeout) clearTimeout(scrollTimeout)
  if (rateToastTimer) clearTimeout(rateToastTimer)
})

const fetchAll = async () => {
  loading.value = overview.value === null
  errorMessage.value = ''
  try {
    const [o, d, a, at, hi] = await Promise.all([
      axios.get<StatsOverview>(`${API_BASE_URL}/stats/overview`),
      axios.get<StatsDistribution>(`${API_BASE_URL}/stats/distribution`),
      axios.get<StatsActivity>(`${API_BASE_URL}/stats/activity`, { params: { days: 365 } }),
      axios.get<StatsAttention>(`${API_BASE_URL}/stats/attention`),
      axios.get<StatsHighlights>(`${API_BASE_URL}/stats/highlights`, { params: { limit: 10 } }),
    ])
    overview.value = o.data
    distribution.value = d.data
    activity.value = a.data
    attention.value = at.data
    highlights.value = hi.data

    const now = new Date()
    lastUpdatedTime.value = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`
  } catch (err: any) {
    errorMessage.value = err?.response?.data?.detail || '加载统计数据失败，请确认后端服务正在运行。'
  } finally {
    loading.value = false
    nextTick(() => initObserver())
  }
}

const refresh = async () => {
  if (refreshSpinning.value) return
  refreshSpinning.value = true
  await fetchAll()
  setTimeout(() => (refreshSpinning.value = false), 400)
}

onMounted(fetchAll)

// ---- Formatters ----
const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes < 1024 ** 4) return `${(bytes / (1024 ** 3)).toFixed(2)} GB`
  return `${(bytes / (1024 ** 4)).toFixed(2)} TB`
}

const formatDurationHours = (seconds: number) => {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h} 小时 ${m} 分`
  return `${m} 分`
}

const typeMeta: Record<string, { label: string; icon: any; color: string }> = {
  video: { label: '视频', icon: Film, color: '#60a5fa' },
  manga: { label: '漫画', icon: Layers, color: '#a78bfa' },
  image: { label: '杂图', icon: ImageIcon, color: '#34d399' },
  audio: { label: '音频', icon: Music, color: '#fbbf24' },
}

const sourceLabel = (key: string) => {
  if (key === 'local') return '本地'
  if (key === 'x') return 'X (推特)'
  if (key === 'wnacg') return 'WNACG'
  if (key === 'asmr') return 'ASMR'
  return key
}

const sourceLinkable = (key: string) => key === 'x' || key === 'wnacg' || key === 'local'

const statusLabel: Record<string, string> = {
  unviewed: '未看',
  viewing: '在看',
  viewed: '已看',
}

// ---- Overview KPIs ----
const overviewCards = computed(() => {
  const o = overview.value
  if (!o) return []

  const total = o.total
  const viewed = o.view_status['viewed'] || 0
  const viewedPct = total > 0 ? ((viewed / total) * 100).toFixed(1) : '0'

  const videoSec = o.total_duration_seconds
  const videoCount = o.by_type['video'] || 0
  const avgVideoSec = videoCount > 0 ? Math.round(videoSec / videoCount) : 0
  const avgVideoMin = (avgVideoSec / 60).toFixed(1)

  const avgSizeBytes = total > 0 ? Math.round(o.total_size_bytes / total) : 0

  return [
    {
      label: '媒体总资产',
      value: total.toLocaleString(),
      unit: '项',
      icon: Layers,
      accent: true,
      sub: `视频 ${o.by_type['video'] || 0} · 漫画 ${o.by_type['manga'] || 0} · 杂图 ${o.by_type['image'] || 0}`,
      to: '/',
    },
    {
      label: '存储总体积',
      value: formatSize(o.total_size_bytes),
      unit: '',
      icon: HardDrive,
      sub: `单项均重约 ${formatSize(avgSizeBytes)}`,
      to: null,
    },
    {
      label: '观看完成度',
      value: `${viewedPct}%`,
      unit: `(${viewed}/${total})`,
      icon: Eye,
      sub: `在看 ${o.view_status['viewing'] || 0} 部 · 未看 ${o.view_status['unviewed'] || 0} 部`,
      to: null,
    },
    {
      label: '视频总时长',
      value: formatDurationHours(videoSec),
      unit: '',
      icon: Clock,
      sub: `均片长约 ${avgVideoMin} 分钟`,
      to: '/type/video',
    },
    {
      label: '特别收藏',
      value: o.favorites.toLocaleString(),
      unit: '部',
      icon: Star,
      sub: total > 0 ? `收藏率 ${((o.favorites / total) * 100).toFixed(1)}%` : '暂无收藏',
      to: '/?favorite=true',
    },
    {
      label: '评分覆盖率',
      value: o.rated > 0 ? `${((o.rated / total) * 100).toFixed(1)}%` : '0%',
      unit: `(${o.rated} 已评)`,
      icon: Sparkles,
      sub: o.rated > 0 ? `平均评分 ${o.average_rating ? o.average_rating.toFixed(2) : '—'} 星` : '打分可激发智能推荐',
      to: null,
    },
  ]
})

// ---- Donut Charts ----
const SLICE_COLORS: Record<string, string> = {
  video: '#60a5fa',   // blue-400
  manga: '#a78bfa',   // violet-400
  image: '#34d399',   // emerald-400
  audio: '#fbbf24',   // amber-400
  x: '#60a5fa',
  wnacg: '#f472b6',   // pink-400
  local: '#94a3b8',   // slate-400
  asmr: '#fbbf24',
  unviewed: '#64748b', // slate-500
  viewing: '#a78bfa',  // violet-400
  viewed: '#34d399',   // emerald-400
}
const FALLBACK_COLOR = '#94a3b8'

interface DonutSliceInput {
  key: string
  label: string
  count: number
  to?: string | null
  valueLabel?: string
}

interface DonutSlice extends DonutSliceInput {
  color: string
  pct: number
  dasharray: string
  dashoffset: string
}

interface DonutData {
  slices: DonutSlice[]
  total: number
  totalLabel: string
  circumference: number
}

const DONUT_RADIUS = 40
const DONUT_CIRCUMFERENCE = 2 * Math.PI * DONUT_RADIUS

const buildDonut = (entries: DonutSliceInput[], totalLabel?: string): DonutData => {
  const visible = entries.filter((e) => e.count > 0)
  const total = visible.reduce((s, e) => s + e.count, 0)
  const C = DONUT_CIRCUMFERENCE
  let cumulative = 0
  const slices: DonutSlice[] = visible.map((e) => {
    const ratio = total > 0 ? e.count / total : 0
    const len = ratio * C
    const slice: DonutSlice = {
      ...e,
      color: SLICE_COLORS[e.key] ?? FALLBACK_COLOR,
      pct: Math.round(ratio * 100),
      dasharray: `${len.toFixed(3)} ${(C - len).toFixed(3)}`,
      dashoffset: (-cumulative).toFixed(3),
    }
    cumulative += len
    return slice
  })
  return {
    slices,
    total,
    totalLabel: totalLabel ?? total.toLocaleString(),
    circumference: C,
  }
}

const typeDonut = computed<DonutData | null>(() => {
  const o = overview.value
  if (!o) return null
  const entries: DonutSliceInput[] = Object.entries(o.by_type).map(([key, count]) => ({
    key,
    label: typeMeta[key]?.label ?? key,
    count,
    to: `/type/${key}`,
  }))
  return buildDonut(entries)
})

const typeSizeDonut = computed<DonutData | null>(() => {
  const o = overview.value
  if (!o) return null
  const entries: DonutSliceInput[] = Object.entries(o.by_type_size)
    .filter(([, bytes]) => bytes > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([key, bytes]) => ({
      key,
      label: typeMeta[key]?.label ?? key,
      count: bytes,
      valueLabel: formatSize(bytes),
      to: `/type/${key}`,
    }))
  return buildDonut(entries, formatSize(o.total_size_bytes))
})

const statusDonut = computed<DonutData | null>(() => {
  const o = overview.value
  if (!o) return null
  const entries: DonutSliceInput[] = Object.entries(o.view_status).map(([key, count]) => ({
    key,
    label: statusLabel[key] ?? key,
    count,
    to: null,
  }))
  return buildDonut(entries)
})

const sourceDonut = computed<DonutData | null>(() => {
  const d = distribution.value
  if (!d) return null
  const entries: DonutSliceInput[] = Object.entries(d.by_source).map(([key, count]) => ({
    key,
    label: sourceLabel(key),
    count,
    to: sourceLinkable(key) ? `/?source=${key}` : null,
  }))
  return buildDonut(entries)
})

const donutCards = computed(() => {
  const out: { id: string; title: string; centerLabel: string; donut: DonutData }[] = []
  if (typeDonut.value && typeDonut.value.slices.length) {
    out.push({ id: 'donut-type', title: '媒体类型构成', centerLabel: '总数', donut: typeDonut.value })
  }
  if (typeSizeDonut.value && typeSizeDonut.value.slices.length) {
    out.push({ id: 'donut-size', title: '存储占用分布', centerLabel: '总体积', donut: typeSizeDonut.value })
  }
  if (statusDonut.value && statusDonut.value.slices.length) {
    out.push({ id: 'donut-status', title: '观看进度分布', centerLabel: '总数', donut: statusDonut.value })
  }
  if (sourceDonut.value && sourceDonut.value.slices.length) {
    out.push({ id: 'donut-source', title: '资源来源渠道', centerLabel: '总数', donut: sourceDonut.value })
  }
  return out
})

// Dynamic Donut Hover Focus
const hoveredDonutSlice = ref<Record<string, DonutSlice | null>>({})

const setDonutHover = (cardId: string, slice: DonutSlice | null) => {
  hoveredDonutSlice.value[cardId] = slice
}

// Storage Space Deep Breakdown
const storageBreakdown = computed(() => {
  const o = overview.value
  if (!o || o.total_size_bytes === 0) return []
  const order = ['video', 'manga', 'image', 'audio']
  return order
    .map((key) => {
      const size = o.by_type_size[key] || 0
      const count = o.by_type[key] || 0
      const pct = ((size / o.total_size_bytes) * 100).toFixed(1)
      const avg = count > 0 ? formatSize(Math.round(size / count)) : '—'
      return {
        key,
        label: typeMeta[key]?.label ?? key,
        color: SLICE_COLORS[key] ?? FALLBACK_COLOR,
        size,
        sizeFormatted: formatSize(size),
        count,
        pct: Number(pct),
        pctFormatted: `${pct}%`,
        avgSize: avg,
        to: `/type/${key}`,
      }
    })
    .filter((item) => item.count > 0 || item.size > 0)
})

// ---- Growth Bar Chart (Major Overhaul) ----
const growthChartMode = ref<'both' | 'monthly' | 'cumulative'>('both')
const hoveredGrowthIndex = ref<number | null>(null)

interface FormattedGrowthPoint {
  index: number
  month: string
  monthShort: string
  fullLabel: string
  added: number
  cumulative: number
  pctOfTotal: string
  momChange: string | null
  isPositiveMom: boolean
  // Geometry coordinates in 800×260 SVG space
  slotX: number
  slotW: number
  cx: number
  barX: number
  barY: number
  barW: number
  barH: number
  lineY: number
}

const SVG_W = 800
const SVG_H = 260
const PAD_L = 55
const PAD_R = 30
const PAD_T = 36
const PAD_B = 44
const PLOT_W = SVG_W - PAD_L - PAD_R
const PLOT_H = SVG_H - PAD_T - PAD_B

const growthData = computed(() => {
  const g = distribution.value?.growth ?? []
  if (g.length === 0) return null

  const totalAdded = g.reduce((sum, item) => sum + item.added, 0)
  const maxAdded = Math.max(1, ...g.map((p) => p.added))
  const maxCum = Math.max(1, ...g.map((p) => p.cumulative))
  const slotW = PLOT_W / g.length
  const barW = Math.max(22, Math.min(52, slotW * 0.46))

  const points: FormattedGrowthPoint[] = g.map((p, i) => {
    const [year, month] = p.month.split('-')
    const fullLabel = `${year}年${parseInt(month, 10)}月`
    const monthShort = i === 0 || month === '01' ? `${year.slice(2)}/${month}` : `${parseInt(month, 10)}月`

    let momChange: string | null = null
    let isPositiveMom = false
    if (i > 0) {
      const prev = g[i - 1].added
      if (prev > 0) {
        const diff = ((p.added - prev) / prev) * 100
        isPositiveMom = diff >= 0
        momChange = diff >= 0 ? `+${diff.toFixed(1)}%` : `${diff.toFixed(1)}%`
      }
    }

    const pctOfTotal = totalAdded > 0 ? ((p.added / totalAdded) * 100).toFixed(1) : '0'
    const cx = PAD_L + i * slotW + slotW / 2
    const slotX = PAD_L + i * slotW
    const barX = cx - barW / 2

    // Compute dynamic bar height based on active mode
    let barH = 0
    let barY = PAD_T + PLOT_H
    if (growthChartMode.value === 'monthly') {
      barH = (p.added / maxAdded) * (PLOT_H * 0.82)
      barY = PAD_T + PLOT_H - barH
    } else if (growthChartMode.value === 'cumulative') {
      barH = (p.cumulative / maxCum) * (PLOT_H * 0.82)
      barY = PAD_T + PLOT_H - barH
    } else {
      // 'both' mode: bars are monthly added (up to 72% height), line is cumulative (up to 95% height)
      barH = (p.added / maxAdded) * (PLOT_H * 0.72)
      barY = PAD_T + PLOT_H - barH
    }

    const lineY = PAD_T + PLOT_H - (p.cumulative / maxCum) * (PLOT_H * 0.9)

    return {
      index: i,
      month: p.month,
      monthShort,
      fullLabel,
      added: p.added,
      cumulative: p.cumulative,
      pctOfTotal,
      momChange,
      isPositiveMom,
      slotX,
      slotW,
      cx,
      barX,
      barY,
      barW,
      barH,
      lineY,
    }
  })

  // Smooth line & area coordinates
  const linePoints = points.map((p) => `${p.cx.toFixed(1)},${p.lineY.toFixed(1)}`).join(' ')
  const areaPoints =
    points.length > 1
      ? `${points[0].cx.toFixed(1)},${(PAD_T + PLOT_H).toFixed(1)} ${linePoints} ${points[points.length - 1].cx.toFixed(1)},${(PAD_T + PLOT_H).toFixed(1)}`
      : ''

  // Y-axis ticks
  const activeMax = growthChartMode.value === 'monthly' ? maxAdded : maxCum
  const yTicks = [
    { y: PAD_T, label: activeMax.toLocaleString() },
    { y: PAD_T + PLOT_H * 0.33, label: Math.round(activeMax * 0.67).toLocaleString() },
    { y: PAD_T + PLOT_H * 0.67, label: Math.round(activeMax * 0.33).toLocaleString() },
    { y: PAD_T + PLOT_H, label: '0' },
  ]

  // KPI highlights
  const maxMonth = points.reduce((best, cur) => (cur.added > best.added ? cur : best), points[0])
  const recent3 = points.slice(-3)
  const avgRecent3 = recent3.length > 0 ? (recent3.reduce((s, p) => s + p.added, 0) / recent3.length).toFixed(1) : '0'

  return {
    points,
    linePoints,
    areaPoints,
    yTicks,
    totalAdded,
    maxAdded,
    maxCum,
    maxMonth,
    avgRecent3,
    monthsCount: g.length,
    latestMonth: points[points.length - 1],
  }
})

// Growth Chart Tooltip
interface GrowthTooltipData {
  visible: boolean
  x: number
  y: number
  point: FormattedGrowthPoint | null
}

const growthTooltip = ref<GrowthTooltipData>({
  visible: false,
  x: 0,
  y: 0,
  point: null,
})

const onGrowthSlotEnter = (point: FormattedGrowthPoint, event: MouseEvent) => {
  hoveredGrowthIndex.value = point.index
  const target = event.currentTarget as SVGElement
  const rect = target.getBoundingClientRect()
  growthTooltip.value = {
    visible: true,
    x: Math.round(rect.left + rect.width / 2),
    y: Math.round(rect.top - 8),
    point,
  }
}

const onGrowthSlotLeave = () => {
  hoveredGrowthIndex.value = null
  growthTooltip.value.visible = false
}

// ---- Activity Heatmap (Major Overhaul with Tooltip & Labels) ----
const heatmapType = ref<'all' | string>('all')

const heatmapTypeTabs = computed(() => {
  const a = activity.value
  const tabs: { key: string; label: string; total: number }[] = [
    { key: 'all', label: '全部', total: a?.total ?? 0 },
  ]
  if (!a) return tabs
  const order = ['video', 'manga', 'image', 'audio']
  for (const key of order) {
    const buckets = a.by_type?.[key]
    if (!buckets || buckets.length === 0) continue
    const total = buckets.reduce((s, b) => s + b.count, 0)
    tabs.push({ key, label: typeMeta[key]?.label ?? key, total })
  }
  return tabs
})

interface HeatmapDay {
  date: string
  count: number
  level: number
  inRange: boolean
  dayOfWeek: number
  formattedDate: string
  dayName: string
}

const weekDayNames = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
const weekDayLabels = ['', '周一', '', '周三', '', '周五', '']

const heatmap = computed(() => {
  const a = activity.value
  if (!a) return null

  const source: StatsActivityBucket[] =
    heatmapType.value === 'all' ? a.buckets : a.by_type?.[heatmapType.value] ?? []
  const counts = new Map<string, number>()
  for (const b of source) counts.set(b.date, b.count)

  const to = new Date(a.to_date + 'T00:00:00')
  const from = new Date(to)
  from.setDate(from.getDate() - (a.days - 1))
  const gridStart = new Date(from)
  gridStart.setDate(gridStart.getDate() - gridStart.getDay())

  const subsetMax = source.length ? Math.max(...source.map((b) => b.count)) : 0
  const subsetTotal = source.reduce((s, b) => s + b.count, 0)
  const max = Math.max(1, subsetMax)
  const level = (c: number) => {
    if (c <= 0) return 0
    const r = c / max
    if (r <= 0.25) return 1
    if (r <= 0.5) return 2
    if (r <= 0.75) return 3
    return 4
  }

  const weeks: HeatmapDay[][] = []
  const cursor = new Date(gridStart)
  while (cursor <= to) {
    const week: HeatmapDay[] = []
    for (let d = 0; d < 7; d++) {
      const iso = cursor.toISOString().slice(0, 10)
      const c = counts.get(iso) ?? 0
      const inRange = cursor >= from && cursor <= to
      const [y, m, dayNum] = iso.split('-').map(Number)
      const dayOfWeek = cursor.getDay()
      week.push({
        date: iso,
        count: c,
        level: inRange ? level(c) : 0,
        inRange,
        dayOfWeek,
        formattedDate: `${y}年${m}月${dayNum}日`,
        dayName: weekDayNames[dayOfWeek],
      })
      cursor.setDate(cursor.getDate() + 1)
    }
    weeks.push(week)
  }

  let activeDays = 0
  for (const w of weeks) {
    for (const d of w) {
      if (d.inRange && d.count > 0) activeDays++
    }
  }

  return {
    weeks,
    total: subsetTotal,
    max: subsetMax,
    activeDays,
    activePct: ((activeDays / a.days) * 100).toFixed(1),
  }
})

// Month markers calculated along the week columns
const monthHeaders = computed(() => {
  if (!heatmap.value) return []
  const headers: { weekIndex: number; label: string }[] = []
  let lastMonth = -1
  heatmap.value.weeks.forEach((week, wi) => {
    const validDay = week.find((d) => d.inRange)
    if (!validDay) return
    const month = parseInt(validDay.date.split('-')[1], 10)
    if (month !== lastMonth) {
      if (headers.length === 0 || wi - headers[headers.length - 1].weekIndex >= 3) {
        headers.push({ weekIndex: wi, label: `${month}月` })
        lastMonth = month
      }
    }
  })
  return headers
})

const levelClass = (lvl: number, inRange: boolean) => {
  if (!inRange) return 'bg-transparent'
  return [
    'bg-white/[0.04] border border-white/[0.05]',
    'bg-accent/25 border border-accent/35',
    'bg-accent/50 border border-accent/60',
    'bg-accent/75 border border-accent/80',
    'bg-accent border border-accent-glow shadow-[0_0_8px_rgba(var(--color-accent),0.45)]',
  ][lvl]
}

// Heatmap Instant Floating Tooltip
interface HeatmapTooltipData {
  visible: boolean
  x: number
  y: number
  day: HeatmapDay | null
}

const heatmapTooltip = ref<HeatmapTooltipData>({
  visible: false,
  x: 0,
  y: 0,
  day: null,
})

const onHeatmapCellEnter = (day: HeatmapDay, event: MouseEvent) => {
  if (!day.inRange) return
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  heatmapTooltip.value = {
    visible: true,
    x: Math.round(rect.left + rect.width / 2),
    y: Math.round(rect.top - 8),
    day,
  }
}

const onHeatmapCellLeave = () => {
  heatmapTooltip.value.visible = false
}

// ---- Ratings & Attention ----
const hasRatings = computed(() => (overview.value?.rated || 0) > 0)

const ratingBars = computed(() => {
  const d = distribution.value
  if (!d) return []
  const entries = Object.entries(d.rating_histogram).sort((a, b) => Number(b[0]) - Number(a[0]))
  const max = Math.max(1, ...entries.map(([, c]) => c))
  return entries.map(([stars, count]) => ({
    stars: Number(stars),
    count,
    pct: Math.round((count / max) * 100),
  }))
})

const attentionFilter = ref<'all' | 'unrated' | 'dusty'>('all')
const hoverStars = ref<Record<number, number>>({})
const ratingLoading = ref<number | null>(null)
const rateToast = ref<string | null>(null)
let rateToastTimer: number | undefined

const quickRate = async (item: StatAttentionItem, stars: number, event: Event) => {
  event.preventDefault()
  event.stopPropagation()
  if (ratingLoading.value === item.id) return
  ratingLoading.value = item.id
  try {
    await axios.patch(`${API_BASE_URL}/media/${item.id}`, { rating: stars })
    item.rating = stars
    rateToast.value = `已为《${item.title}》评分 ${stars} 星 ✨`
    window.clearTimeout(rateToastTimer)
    rateToastTimer = window.setTimeout(() => {
      rateToast.value = null
    }, 2500)
    setTimeout(() => {
      if (attention.value) {
        attention.value.unrated = attention.value.unrated.filter((i) => i.id !== item.id)
      }
    }, 500)
  } catch {
    // non-fatal
  } finally {
    ratingLoading.value = null
  }
}

const creatorLink = (c: { kind: string; screen_name: string | null }) =>
  c.kind === 'x' && c.screen_name ? `/creators/${c.screen_name}` : null

const formatDurationShort = (seconds: number) => {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  return `${m}:${s.toString().padStart(2, '0')}`
}

const lastOpenedText = (item: StatAttentionItem) => {
  if (!item.last_opened_at) return '从未打开'
  const d = new Date(item.last_opened_at)
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (days <= 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 30) return `${days} 天前`
  if (days < 365) return `${Math.floor(days / 30)} 个月前`
  return `${Math.floor(days / 365)} 年前`
}
</script>

<template>
  <div class="p-6 md:p-8 max-w-7xl mx-auto space-y-10">
    <!-- 头部区域 -->
    <div class="he-page-header flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-2xl sm:text-3xl font-black text-white flex items-center gap-3">
          <BarChart3 :size="28" class="text-accent" />
          统计与数据看板
        </h1>
        <p class="text-white/50 text-sm mt-1 flex items-center gap-2">
          <span>媒体库资产透视 · 存储占用 · 入库增长 · 活跃轨迹</span>
          <span v-if="lastUpdatedTime" class="text-xs text-white/35 font-mono">
            (更新于 {{ lastUpdatedTime }})
          </span>
        </p>
      </div>

      <div class="flex items-center gap-3">
        <button
          @click="refresh"
          class="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-white/70 hover:text-white hover:bg-white/[0.08] hover:border-white/20 hover:shadow-lg transition-all cursor-pointer text-xs font-bold"
          title="刷新全部统计数据"
        >
          <RefreshCw :size="15" :class="{ 'animate-spin': refreshSpinning }" />
          <span>刷新数据</span>
        </button>
      </div>
    </div>

    <!-- 吸顶导航条 -->
    <div
      v-if="!loading && !errorMessage"
      class="sticky top-2 z-30 p-1.5 rounded-2xl bg-sidebar/85 backdrop-blur-2xl border border-white/10 shadow-xl shadow-black/35 flex items-center gap-1.5 overflow-x-auto custom-scrollbar"
    >
      <button
        v-for="item in navSections"
        :key="item.id"
        type="button"
        @click="scrollToSection(item.id)"
        class="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all whitespace-nowrap cursor-pointer select-none"
        :class="activeSection === item.id
          ? 'bg-accent text-white shadow-md shadow-accent/30'
          : 'text-white/60 hover:text-white hover:bg-white/5'"
      >
        <component :is="item.icon" :size="14" />
        <span>{{ item.label }}</span>
      </button>
    </div>

    <!-- 加载与错误状态 -->
    <div v-if="loading" class="text-white/40 py-28 text-center space-y-3">
      <RefreshCw :size="28" class="animate-spin mx-auto text-accent/70" />
      <div class="text-sm font-bold text-white/70">正在深度汇总媒体库统计…</div>
    </div>
    <div
      v-else-if="errorMessage"
      class="py-16 text-center text-red-200 bg-red-500/10 border border-red-500/20 rounded-2xl"
    >
      {{ errorMessage }}
    </div>

    <!-- 主内容区 -->
    <div v-else class="space-y-12">
      <!-- ==========================================
           1. 概览指标 (Overview Key Metrics)
           ========================================== -->
      <section id="section-overview" class="scroll-mt-24 space-y-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <BarChart3 :size="18" class="text-accent" />
            <h2 class="text-sm font-black tracking-wider uppercase text-white/70">核心概览</h2>
          </div>
          <span class="text-xs text-white/40">点击卡片可快速穿梭至对应分类</span>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          <component
            :is="card.to ? RouterLink : 'div'"
            v-for="card in overviewCards"
            :key="card.label"
            :to="card.to ?? undefined"
            class="group rounded-2xl p-4.5 border border-white/8 bg-white/[0.02] backdrop-blur-3xl shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_8px_24px_-8px_rgba(0,0,0,0.3)] transition-all duration-300 relative overflow-hidden flex flex-col justify-between"
            :class="[
              card.accent ? 'border-accent/40 bg-accent/[0.03] shadow-accent/5' : '',
              card.to ? 'hover:bg-white/[0.06] hover:border-white/20 hover:-translate-y-1 cursor-pointer' : '',
            ]"
          >
            <div>
              <div class="flex items-center justify-between mb-3">
                <component :is="card.icon" :size="18" class="text-accent group-hover:scale-110 transition-transform" />
                <ArrowUpRight v-if="card.to" :size="14" class="text-white/25 group-hover:text-accent transition-colors" />
              </div>
              <div class="flex items-baseline gap-1">
                <span class="text-xl sm:text-2xl font-black text-white leading-tight tracking-tight break-words">
                  {{ card.value }}
                </span>
                <span v-if="card.unit" class="text-xs text-white/50 font-semibold">{{ card.unit }}</span>
              </div>
              <div class="text-xs text-white/50 font-bold mt-1">{{ card.label }}</div>
            </div>
            <div class="text-[11px] text-white/35 font-medium mt-3 pt-2.5 border-t border-white/5 truncate" :title="card.sub">
              {{ card.sub }}
            </div>
          </component>
        </div>
      </section>

      <!-- ==========================================
           2. 资产分布 (Donut Charts & Storage Breakdown)
           ========================================== -->
      <section id="section-distribution" class="scroll-mt-24 space-y-6">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <PieChart :size="18" class="text-accent" />
            <h2 class="text-sm font-black tracking-wider uppercase text-white/70">资产结构与空间透视</h2>
          </div>
          <span class="text-xs text-white/40">悬停饼图扇区可查看中心聚合详情</span>
        </div>

        <!-- 4 组 Donut 环形图 -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div
            v-for="card in donutCards"
            :key="card.id"
            class="rounded-3xl p-6 bg-white/[0.02] backdrop-blur-3xl border border-white/8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)] flex flex-col justify-between"
          >
            <div class="flex items-center justify-between mb-5">
              <h3 class="text-xs font-black tracking-wider uppercase text-white/60">{{ card.title }}</h3>
              <span class="text-[11px] text-white/35 font-mono">共 {{ card.donut.slices.length }} 项</span>
            </div>

            <div class="flex items-center gap-6">
              <!-- Donut Chart -->
              <div class="relative w-[136px] h-[136px] shrink-0">
                <svg viewBox="0 0 100 100" class="w-full h-full -rotate-90">
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    fill="none"
                    stroke="rgba(255,255,255,0.04)"
                    stroke-width="14"
                  />
                  <circle
                    v-for="s in card.donut.slices"
                    :key="s.key"
                    cx="50"
                    cy="50"
                    r="40"
                    fill="none"
                    stroke-linecap="butt"
                    :stroke="s.color"
                    :stroke-width="hoveredDonutSlice[card.id]?.key === s.key ? 17 : 14"
                    :stroke-dasharray="s.dasharray"
                    :stroke-dashoffset="s.dashoffset"
                    class="transition-all duration-300 cursor-pointer"
                    :style="{
                      filter: hoveredDonutSlice[card.id]?.key === s.key ? 'brightness(1.25) drop-shadow(0 0 6px currentColor)' : 'none',
                    }"
                    @mouseenter="setDonutHover(card.id, s)"
                    @mouseleave="setDonutHover(card.id, null)"
                  />
                </svg>

                <!-- Center label -->
                <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none p-2 text-center">
                  <template v-if="hoveredDonutSlice[card.id]">
                    <div
                      class="text-base sm:text-lg font-black leading-none tracking-tight truncate max-w-full"
                      :style="{ color: hoveredDonutSlice[card.id]?.color }"
                    >
                      {{ hoveredDonutSlice[card.id]?.valueLabel ?? hoveredDonutSlice[card.id]?.count.toLocaleString() }}
                    </div>
                    <div class="text-[10px] font-bold text-white/60 mt-1 truncate max-w-full">
                      {{ hoveredDonutSlice[card.id]?.label }} ({{ hoveredDonutSlice[card.id]?.pct }}%)
                    </div>
                  </template>
                  <template v-else>
                    <div class="text-base sm:text-lg font-black text-white leading-none tracking-tight">
                      {{ card.donut.totalLabel }}
                    </div>
                    <div class="text-[10px] text-white/40 mt-1 font-bold uppercase tracking-wider">
                      {{ card.centerLabel }}
                    </div>
                  </template>
                </div>
              </div>

              <!-- Legend List -->
              <ul class="flex-1 space-y-2.5 min-w-0">
                <li
                  v-for="s in card.donut.slices"
                  :key="s.key"
                  @mouseenter="setDonutHover(card.id, s)"
                  @mouseleave="setDonutHover(card.id, null)"
                >
                  <component
                    :is="s.to ? RouterLink : 'div'"
                    :to="s.to ?? undefined"
                    class="flex items-center gap-2.5 text-xs p-1.5 rounded-xl group transition-all"
                    :class="[
                      hoveredDonutSlice[card.id]?.key === s.key ? 'bg-white/10' : 'hover:bg-white/5',
                      s.to ? 'cursor-pointer' : '',
                    ]"
                  >
                    <span
                      class="w-2.5 h-2.5 rounded-full shrink-0 transition-transform"
                      :class="hoveredDonutSlice[card.id]?.key === s.key ? 'scale-125' : ''"
                      :style="{ backgroundColor: s.color }"
                    />
                    <span
                      class="text-white/80 font-bold truncate group-hover:text-white"
                      :class="s.to ? 'group-hover:text-accent' : ''"
                    >
                      {{ s.label }}
                    </span>
                    <span class="ml-auto text-white/50 font-bold tabular-nums shrink-0 text-xs">
                      {{ s.valueLabel ?? s.count.toLocaleString() }}
                      <span class="text-white/35 font-normal ml-1">· {{ s.pct }}%</span>
                    </span>
                  </component>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <!-- 存储空间深度透视 (Storage Breakdown Cards) -->
        <div
          v-if="storageBreakdown.length"
          class="rounded-3xl p-6 bg-white/[0.02] backdrop-blur-3xl border border-white/8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)] space-y-5"
        >
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <HardDrive :size="16" class="text-accent" />
              <h3 class="text-xs font-black tracking-wider uppercase text-white/70">各类媒体存储占用与单项均重</h3>
            </div>
            <span class="text-xs text-white/40 font-mono">
              全库共 {{ formatSize(overview?.total_size_bytes || 0) }}
            </span>
          </div>

          <!-- 堆叠进度条 -->
          <div class="h-3 rounded-full bg-white/5 overflow-hidden flex p-0.5 gap-0.5 border border-white/10">
            <div
              v-for="item in storageBreakdown"
              :key="item.key"
              class="h-full first:rounded-l-full last:rounded-r-full transition-all duration-500 hover:brightness-125 cursor-pointer"
              :style="{ width: `${item.pct}%`, backgroundColor: item.color }"
              :title="`${item.label}: ${item.sizeFormatted} (${item.pctFormatted})`"
            />
          </div>

          <!-- 4列明细指标 -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4 pt-1">
            <RouterLink
              v-for="item in storageBreakdown"
              :key="item.key"
              :to="item.to"
              class="p-3.5 rounded-2xl bg-white/[0.02] border border-white/5 hover:bg-white/[0.06] hover:border-white/15 transition-all group cursor-pointer block"
            >
              <div class="flex items-center justify-between mb-2">
                <span class="text-xs font-bold text-white/70 flex items-center gap-1.5">
                  <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: item.color }" />
                  {{ item.label }}
                </span>
                <span class="text-[11px] font-bold text-white/40 font-mono">{{ item.pctFormatted }}</span>
              </div>
              <div class="text-lg font-black text-white group-hover:text-accent transition-colors">
                {{ item.sizeFormatted }}
              </div>
              <div class="text-[11px] text-white/40 mt-1 font-medium flex items-center justify-between">
                <span>{{ item.count }} 项</span>
                <span>均重 {{ item.avgSize }}</span>
              </div>
            </RouterLink>
          </div>
        </div>
      </section>

      <!-- ==========================================
           3. 入库增长趋势 (柱状图重构 - Growth Bar Chart)
           ========================================== -->
      <section id="section-growth" class="scroll-mt-24 space-y-6">
        <div class="flex items-center justify-between flex-wrap gap-3">
          <div class="flex items-center gap-2">
            <TrendingUp :size="18" class="text-accent" />
            <h2 class="text-sm font-black tracking-wider uppercase text-white/70">入库增长趋势分析</h2>
          </div>

          <!-- 视图模式切换器 -->
          <div class="flex items-center gap-1 bg-white/[0.03] border border-white/10 rounded-xl p-1 shadow-inner">
            <button
              type="button"
              @click="growthChartMode = 'both'"
              class="px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer"
              :class="growthChartMode === 'both' ? 'bg-accent text-white shadow-md shadow-accent/20' : 'text-white/60 hover:text-white'"
            >
              ⚡ 复合趋势 (柱+线)
            </button>
            <button
              type="button"
              @click="growthChartMode = 'monthly'"
              class="px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer"
              :class="growthChartMode === 'monthly' ? 'bg-accent text-white shadow-md shadow-accent/20' : 'text-white/60 hover:text-white'"
            >
              📊 月度新增 (柱状)
            </button>
            <button
              type="button"
              @click="growthChartMode = 'cumulative'"
              class="px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer"
              :class="growthChartMode === 'cumulative' ? 'bg-accent text-white shadow-md shadow-accent/20' : 'text-white/60 hover:text-white'"
            >
              📈 累计总量 (曲线)
            </button>
          </div>
        </div>

        <div class="rounded-3xl p-6 bg-white/[0.02] backdrop-blur-3xl border border-white/8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)] space-y-6">
          <!-- 增长 KPI 快速洞察条 -->
          <div v-if="growthData" class="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3.5 rounded-2xl bg-white/[0.02] border border-white/5">
            <div>
              <div class="text-[11px] text-white/40 font-bold">历史入库总量</div>
              <div class="text-lg font-black text-white mt-0.5">
                {{ growthData.totalAdded.toLocaleString() }} <span class="text-xs font-normal text-white/40">部</span>
              </div>
            </div>
            <div>
              <div class="text-[11px] text-white/40 font-bold">最高单月新增</div>
              <div class="text-lg font-black text-accent mt-0.5">
                {{ growthData.maxMonth.added.toLocaleString() }} <span class="text-xs font-normal text-white/40">({{ growthData.maxMonth.month }})</span>
              </div>
            </div>
            <div>
              <div class="text-[11px] text-white/40 font-bold">近 3 个月月均</div>
              <div class="text-lg font-black text-white mt-0.5">
                {{ growthData.avgRecent3 }} <span class="text-xs font-normal text-white/40">部/月</span>
              </div>
            </div>
            <div>
              <div class="text-[11px] text-white/40 font-bold">最新月份入库</div>
              <div class="text-lg font-black text-emerald-400 mt-0.5">
                +{{ growthData.latestMonth.added.toLocaleString() }} <span class="text-xs font-normal text-white/40">({{ growthData.latestMonth.month }})</span>
              </div>
            </div>
          </div>

          <!-- 交互式 SVG 柱状与折线图表 -->
          <div v-if="growthData" class="relative">
            <svg
              viewBox="0 0 800 260"
              preserveAspectRatio="xMidYMid meet"
              class="w-full h-56 sm:h-72 overflow-visible select-none"
            >
              <defs>
                <!-- 柱状渐变 -->
                <linearGradient id="growthBarGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="rgb(var(--color-accent))" stop-opacity="0.9" />
                  <stop offset="100%" stop-color="rgb(var(--color-accent))" stop-opacity="0.3" />
                </linearGradient>
                <!-- 激活柱状高亮渐变 -->
                <linearGradient id="growthBarActiveGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95" />
                  <stop offset="100%" stop-color="rgb(var(--color-accent))" stop-opacity="0.7" />
                </linearGradient>
                <!-- 面积渐变 -->
                <linearGradient id="growthAreaGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="rgb(var(--color-accent))" stop-opacity="0.35" />
                  <stop offset="100%" stop-color="rgb(var(--color-accent))" stop-opacity="0.0" />
                </linearGradient>
                <!-- 滤镜发光 -->
                <filter id="glowEffect" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
              </defs>

              <!-- Y-Axis 背景参考网格线 -->
              <g class="grid-lines">
                <template v-for="(tick, idx) in growthData.yTicks" :key="idx">
                  <line
                    :x1="PAD_L"
                    :y1="tick.y"
                    :x2="SVG_W - PAD_R"
                    :y2="tick.y"
                    stroke="rgba(255,255,255,0.07)"
                    stroke-dasharray="4 4"
                    stroke-width="1"
                  />
                  <text
                    :x="PAD_L - 8"
                    :y="tick.y + 4"
                    text-anchor="end"
                    class="text-[10px] font-mono fill-white/35 font-bold"
                  >
                    {{ tick.label }}
                  </text>
                </template>
              </g>

              <!-- 累计折线下方渐变面积 (复合模式与累计模式下可见) -->
              <template v-if="growthChartMode !== 'monthly' && growthData.areaPoints">
                <polygon :points="growthData.areaPoints" fill="url(#growthAreaGrad)" />
              </template>

              <!-- 柱状图矩形与交互槽位 -->
              <g class="bars-group">
                <template v-for="p in growthData.points" :key="p.month">
                  <!-- 悬停指示背景带 -->
                  <rect
                    :x="p.slotX"
                    :y="PAD_T"
                    :width="p.slotW"
                    :height="PLOT_H"
                    class="transition-colors duration-200 cursor-pointer"
                    :fill="hoveredGrowthIndex === p.index ? 'rgba(255,255,255,0.05)' : 'transparent'"
                    rx="6"
                    @mouseenter="onGrowthSlotEnter(p, $event)"
                    @mouseleave="onGrowthSlotLeave"
                  />

                  <!-- 实体柱子 (复合模式与月度新增模式显示新增，累计模式显示累计) -->
                  <rect
                    :x="p.barX"
                    :y="p.barY"
                    :width="p.barW"
                    :height="p.barH"
                    rx="5"
                    class="transition-all duration-300 pointer-events-none"
                    :fill="hoveredGrowthIndex === p.index ? 'url(#growthBarActiveGrad)' : 'url(#growthBarGrad)'"
                    :style="{
                      filter: hoveredGrowthIndex === p.index ? 'url(#glowEffect)' : 'none',
                    }"
                  />

                  <!-- 柱顶常显/高显数字标签 -->
                  <text
                    :x="p.cx"
                    :y="p.barY - 8"
                    text-anchor="middle"
                    class="text-[10px] font-mono font-bold transition-all duration-200 pointer-events-none"
                    :class="hoveredGrowthIndex === p.index ? 'fill-white font-extrabold text-[12px]' : 'fill-white/60'"
                  >
                    {{ (growthChartMode === 'cumulative' ? p.cumulative : p.added).toLocaleString() }}
                  </text>

                  <!-- X-Axis 月份标签 -->
                  <text
                    :x="p.cx"
                    :y="SVG_H - 12"
                    text-anchor="middle"
                    class="text-[11px] font-bold transition-all duration-200 pointer-events-none"
                    :class="hoveredGrowthIndex === p.index ? 'fill-accent font-black' : 'fill-white/45'"
                  >
                    {{ p.monthShort }}
                  </text>
                </template>
              </g>

              <!-- 累计折线 Polyline (复合模式与累计模式下可见) -->
              <template v-if="growthChartMode !== 'monthly' && growthData.linePoints">
                <polyline
                  :points="growthData.linePoints"
                  fill="none"
                  stroke="#ffffff"
                  stroke-width="2.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  class="transition-all duration-500"
                  style="filter: drop-shadow(0 0 6px rgba(255,255,255,0.5));"
                />

                <!-- 折线上的数据圆点 -->
                <circle
                  v-for="p in growthData.points"
                  :key="'dot-' + p.month"
                  :cx="p.cx"
                  :cy="p.lineY"
                  :r="hoveredGrowthIndex === p.index ? 6 : 4"
                  fill="#ffffff"
                  stroke="rgb(var(--color-accent))"
                  :stroke-width="hoveredGrowthIndex === p.index ? 3 : 2"
                  class="transition-all duration-200 pointer-events-none"
                />
              </template>
            </svg>

            <!-- 图例说明 -->
            <div class="flex items-center justify-between text-xs text-white/40 pt-2 border-t border-white/5 px-2">
              <div class="flex items-center gap-4">
                <span class="flex items-center gap-1.5 font-medium">
                  <span class="w-3 h-3 rounded bg-accent/70" />
                  {{ growthChartMode === 'cumulative' ? '当月累计体量' : '当月入库新增' }}
                </span>
                <span v-if="growthChartMode === 'both'" class="flex items-center gap-1.5 font-medium">
                  <span class="w-3 h-0.5 bg-white shadow-[0_0_4px_#fff]" />
                  累计全库总量
                </span>
              </div>
              <span class="font-mono text-[11px]">
                共统计 {{ growthData.monthsCount }} 个自然月度
              </span>
            </div>
          </div>

          <div v-else class="text-white/40 text-sm py-12 text-center">
            暂无入库时间跨度数据。
          </div>
        </div>
      </section>

      <!-- ==========================================
           4. 活跃热力图 (近一年活跃度 - Heatmap Overhaul)
           ========================================== -->
      <section id="section-activity" class="scroll-mt-24 space-y-6">
        <div class="flex items-center justify-between flex-wrap gap-3">
          <div class="flex items-center gap-2">
            <Flame :size="18" class="text-accent" />
            <h2 class="text-sm font-black tracking-wider uppercase text-white/70">近一年活跃轨迹热力图</h2>
          </div>

          <!-- 分类筛选器 -->
          <div class="flex items-center gap-1 bg-white/[0.03] border border-white/10 rounded-xl p-1 shadow-inner">
            <button
              v-for="tab in heatmapTypeTabs"
              :key="tab.key"
              @click="heatmapType = tab.key"
              class="px-3 py-1 rounded-lg text-xs font-bold transition-all tabular-nums cursor-pointer flex items-center gap-1.5"
              :class="heatmapType === tab.key
                ? 'bg-accent text-white shadow-md shadow-accent/20'
                : 'text-white/60 hover:text-white'"
            >
              <span>{{ tab.label }}</span>
              <span class="text-[10px] opacity-75 font-mono">({{ tab.total.toLocaleString() }})</span>
            </button>
          </div>
        </div>

        <div class="rounded-3xl p-6 bg-white/[0.02] backdrop-blur-3xl border border-white/8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)] space-y-5">
          <!-- 活跃统计卡片 -->
          <div v-if="heatmap" class="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3.5 rounded-2xl bg-white/[0.02] border border-white/5">
            <div>
              <div class="text-[11px] text-white/40 font-bold">过去一年打开总量</div>
              <div class="text-lg font-black text-white mt-0.5">
                {{ heatmap.total.toLocaleString() }} <span class="text-xs font-normal text-white/40">次</span>
              </div>
            </div>
            <div>
              <div class="text-[11px] text-white/40 font-bold">实际活跃天数</div>
              <div class="text-lg font-black text-accent mt-0.5">
                {{ heatmap.activeDays }} <span class="text-xs font-normal text-white/40">天 ({{ heatmap.activePct }}%)</span>
              </div>
            </div>
            <div>
              <div class="text-[11px] text-white/40 font-bold">单日最高峰值</div>
              <div class="text-lg font-black text-amber-300 mt-0.5">
                {{ heatmap.max }} <span class="text-xs font-normal text-white/40">次/日</span>
              </div>
            </div>
            <div>
              <div class="text-[11px] text-white/40 font-bold">当前筛选模式</div>
              <div class="text-lg font-black text-white/90 mt-0.5">
                {{ heatmapType === 'all' ? '全部媒体' : typeMeta[heatmapType]?.label ?? heatmapType }}
              </div>
            </div>
          </div>

          <!-- 热力图本体 (带月份标头 + 星期侧标 + 鼠标即时浮窗) -->
          <div v-if="heatmap" class="overflow-x-auto custom-scrollbar pb-3 pt-1 select-none">
            <div class="inline-block min-w-max">
              <!-- 月份标尺 -->
              <div class="relative h-5 mb-1.5 ml-8 pointer-events-none">
                <span
                  v-for="m in monthHeaders"
                  :key="m.weekIndex"
                  class="absolute text-[11px] font-bold text-white/50 tracking-wider font-mono"
                  :style="{ left: `${m.weekIndex * 15}px` }"
                >
                  {{ m.label }}
                </span>
              </div>

              <!-- 星期侧标 + 热力网格 -->
              <div class="flex items-start">
                <!-- 星期标签 (周一、周三、周五) -->
                <div class="flex flex-col gap-[3px] pr-2.5 text-[10px] text-white/40 font-bold text-right w-8 shrink-0 select-none">
                  <span
                    v-for="(label, idx) in weekDayLabels"
                    :key="idx"
                    class="h-[12px] leading-[12px]"
                  >
                    {{ label }}
                  </span>
                </div>

                <!-- 52周网格 -->
                <div class="flex gap-[3px]">
                  <div
                    v-for="(week, wi) in heatmap.weeks"
                    :key="wi"
                    class="flex flex-col gap-[3px]"
                  >
                    <div
                      v-for="day in week"
                      :key="day.date"
                      class="w-[12px] h-[12px] rounded-[2.5px] transition-all duration-150 cursor-pointer"
                      :class="[
                        levelClass(day.level, day.inRange),
                        day.inRange ? 'hover:scale-135 hover:z-20 hover:ring-2 hover:ring-white/80' : 'pointer-events-none',
                      ]"
                      @mouseenter="onHeatmapCellEnter(day, $event)"
                      @mouseleave="onHeatmapCellLeave"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 底部图例 -->
          <div class="flex items-center justify-between text-xs text-white/40 pt-2 border-t border-white/5 flex-wrap gap-2">
            <span class="font-medium">
              鼠标移至方格上即可即时查看对应日期与打开次数
            </span>
            <div class="flex items-center gap-1.5 ml-auto">
              <span>少</span>
              <div class="w-[11px] h-[11px] rounded-[2px] bg-white/[0.04] border border-white/[0.05]" />
              <div class="w-[11px] h-[11px] rounded-[2px] bg-accent/25 border border-accent/35" />
              <div class="w-[11px] h-[11px] rounded-[2px] bg-accent/50 border border-accent/60" />
              <div class="w-[11px] h-[11px] rounded-[2px] bg-accent/75 border border-accent/80" />
              <div class="w-[11px] h-[11px] rounded-[2px] bg-accent border border-accent-glow shadow-[0_0_6px_rgba(var(--color-accent),0.4)]" />
              <span>多</span>
            </div>
          </div>
        </div>
      </section>

      <!-- ==========================================
           5. 重点整理与库亮点 (Highlights & Attention)
           ========================================== -->
      <section id="section-attention" class="scroll-mt-24 space-y-8">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Sparkles :size="18" class="text-accent" />
            <h2 class="text-sm font-black tracking-wider uppercase text-white/70">重点关注与库亮点</h2>
          </div>
        </div>

        <!-- 亮点三列卡片: Top创作者 / 最长视频 / 评分分布 -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Top 创作者 -->
          <div
            v-if="highlights?.top_creators?.length"
            class="rounded-3xl p-6 bg-white/[0.02] backdrop-blur-3xl border border-white/8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)] flex flex-col justify-between"
          >
            <div>
              <div class="flex items-center justify-between mb-1">
                <h3 class="text-xs font-black tracking-wider uppercase text-white/60">热门创作者</h3>
                <span class="text-[10px] font-bold text-accent px-2 py-0.5 rounded-full bg-accent/10 border border-accent/20">
                  按作品数排行
                </span>
              </div>
              <p class="text-xs text-white/40 mb-4">入库数量最多的创作者与画师</p>

              <ol class="space-y-3">
                <li
                  v-for="(c, idx) in highlights.top_creators.slice(0, 5)"
                  :key="c.key"
                  class="flex items-center gap-3"
                >
                  <span
                    class="w-5 text-center text-xs font-black tabular-nums"
                    :class="[
                      idx === 0 ? 'text-amber-400' : '',
                      idx === 1 ? 'text-slate-300' : '',
                      idx === 2 ? 'text-amber-600' : '',
                      idx > 2 ? 'text-white/35' : '',
                    ]"
                  >
                    #{{ idx + 1 }}
                  </span>
                  <component
                    :is="creatorLink(c) ? RouterLink : 'div'"
                    :to="creatorLink(c) ?? undefined"
                    class="flex items-center gap-3 flex-1 min-w-0 group cursor-pointer"
                  >
                    <div class="w-10 h-10 rounded-xl overflow-hidden bg-black/40 shrink-0 border border-white/10 shadow-inner">
                      <img
                        v-if="c.cover_path"
                        :src="thumbnailUrl(c.cover_path)"
                        class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-300"
                        loading="eager"
                        decoding="async"
                      />
                    </div>
                    <div class="flex-1 min-w-0">
                      <div
                        class="text-sm text-white/85 font-bold truncate group-hover:text-accent transition-colors"
                        :title="c.display_name"
                      >
                        {{ c.display_name }}
                      </div>
                      <div class="text-[10px] text-white/40 font-semibold mt-0.5">
                        {{ c.kind === 'x' ? 'X (推特) 创作者' : '漫画作者' }}
                      </div>
                    </div>
                    <span class="text-xs text-white/60 font-bold tabular-nums shrink-0 bg-white/5 px-2.5 py-1 rounded-lg border border-white/10">
                      {{ c.media_count.toLocaleString() }} 部
                    </span>
                  </component>
                </li>
              </ol>
            </div>
          </div>

          <!-- 最长视频 -->
          <div
            v-if="highlights?.top_videos?.length"
            class="rounded-3xl p-6 bg-white/[0.02] backdrop-blur-3xl border border-white/8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)] flex flex-col justify-between"
          >
            <div>
              <div class="flex items-center justify-between mb-1">
                <h3 class="text-xs font-black tracking-wider uppercase text-white/60">最长视频排行</h3>
                <span class="text-[10px] font-bold text-accent px-2 py-0.5 rounded-full bg-accent/10 border border-accent/20">
                  按播放时长
                </span>
              </div>
              <p class="text-xs text-white/40 mb-4">库内时长最长的影视与录播作品</p>

              <ol class="space-y-3">
                <li
                  v-for="(v, idx) in highlights.top_videos.slice(0, 5)"
                  :key="v.id"
                  class="flex items-center gap-3"
                >
                  <span
                    class="w-5 text-center text-xs font-black tabular-nums"
                    :class="[
                      idx === 0 ? 'text-amber-400' : '',
                      idx === 1 ? 'text-slate-300' : '',
                      idx === 2 ? 'text-amber-600' : '',
                      idx > 2 ? 'text-white/35' : '',
                    ]"
                  >
                    #{{ idx + 1 }}
                  </span>
                  <RouterLink
                    :to="`/?media=${v.id}`"
                    class="flex items-center gap-3 flex-1 min-w-0 group cursor-pointer"
                  >
                    <div class="w-12 h-9 rounded-xl overflow-hidden bg-black/40 shrink-0 border border-white/10 shadow-inner">
                      <img
                        v-if="v.cover_path"
                        :src="thumbnailUrl(v.cover_path)"
                        class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-300"
                        loading="eager"
                        decoding="async"
                      />
                    </div>
                    <div class="flex-1 min-w-0">
                      <div class="text-xs font-bold text-white/85 group-hover:text-accent transition-colors truncate" :title="v.title">
                        {{ v.title }}
                      </div>
                      <div class="text-[10px] text-white/40 font-semibold mt-0.5">{{ formatSize(v.file_size) }}</div>
                    </div>
                    <span class="text-xs text-white/60 font-mono font-bold tabular-nums shrink-0 bg-white/5 px-2 py-0.5 rounded-lg border border-white/10">
                      {{ formatDurationShort(v.duration) }}
                    </span>
                  </RouterLink>
                </li>
              </ol>
            </div>
          </div>

          <!-- 评分分布卡片 -->
          <div
            class="rounded-3xl p-6 bg-white/[0.02] backdrop-blur-3xl border border-white/8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)] flex flex-col justify-between"
          >
            <div>
              <div class="flex items-center justify-between mb-1">
                <h3 class="text-xs font-black tracking-wider uppercase text-white/60">评分分布体系</h3>
                <span class="text-[10px] font-bold text-amber-400 px-2 py-0.5 rounded-full bg-amber-400/10 border border-amber-400/20">
                  星级统计
                </span>
              </div>
              <p class="text-xs text-white/40 mb-4">按 1-5 星评价的媒体分布概览</p>

              <div v-if="hasRatings" class="space-y-3">
                <div v-for="r in ratingBars" :key="r.stars" class="flex items-center gap-3">
                  <span class="flex items-center gap-0.5 w-20 shrink-0 text-amber-300">
                    <template v-if="r.stars > 0">
                      <Star v-for="n in r.stars" :key="n" :size="12" fill="currentColor" />
                    </template>
                    <span v-else class="text-white/40 text-xs font-semibold">未打分</span>
                  </span>
                  <div class="flex-1 h-2 rounded-full bg-white/[0.03] border border-white/5 overflow-hidden">
                    <div
                      class="h-full rounded-full bg-gradient-to-r from-amber-400 to-amber-300 transition-all duration-500 shadow-[0_0_10px_rgba(251,191,36,0.3)]"
                      :style="{ width: `${r.pct}%` }"
                    />
                  </div>
                  <span class="w-12 text-right text-white/60 font-bold text-xs tabular-nums">{{ r.count }}</span>
                </div>
              </div>

              <div v-else class="rounded-2xl border border-dashed border-white/10 bg-white/[0.015] px-5 py-7 text-center">
                <Sparkles :size="24" class="mx-auto text-amber-400/80 mb-2.5" />
                <p class="text-xs font-bold text-white/80">目前全库尚未评星</p>
                <p class="text-[11px] text-white/40 mt-1 mb-4">
                  为已看过的作品评星，能让个性化推荐更加精准。
                </p>
                <a
                  href="#attention-unrated-list"
                  class="inline-flex items-center gap-1.5 h-8 px-3.5 rounded-xl bg-accent/15 border border-accent/25 text-xs font-bold text-accent hover:bg-accent/25 transition-all"
                >
                  <span>去下方打分</span>
                  <ArrowUpRight :size="12" />
                </a>
              </div>
            </div>
          </div>
        </div>

        <!-- 待整理清单 (看后未评 & 尘封高分作品) -->
        <div v-if="attention && (attention.unrated.length || attention.dusty.length)" class="space-y-6">
          <!-- 筛选切换 -->
          <div class="flex items-center justify-between flex-wrap gap-2 pt-4 border-t border-white/5">
            <div class="flex items-center gap-2">
              <Clock :size="16" class="text-accent" />
              <h3 class="text-xs font-black tracking-wider uppercase text-white/70">媒体库待办整理清单</h3>
            </div>
            <div class="flex items-center gap-1 bg-white/[0.03] border border-white/10 rounded-xl p-1">
              <button
                type="button"
                @click="attentionFilter = 'all'"
                class="px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer"
                :class="attentionFilter === 'all' ? 'bg-accent text-white shadow-sm' : 'text-white/60 hover:text-white'"
              >
                全部
              </button>
              <button
                v-if="attention.unrated.length"
                type="button"
                @click="attentionFilter = 'unrated'"
                class="px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer"
                :class="attentionFilter === 'unrated' ? 'bg-accent text-white shadow-sm' : 'text-white/60 hover:text-white'"
              >
                已看未评 ({{ attention.unrated.length }})
              </button>
              <button
                v-if="attention.dusty.length"
                type="button"
                @click="attentionFilter = 'dusty'"
                class="px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer"
                :class="attentionFilter === 'dusty' ? 'bg-accent text-white shadow-sm' : 'text-white/60 hover:text-white'"
              >
                尘封高分 ({{ attention.dusty.length }})
              </button>
            </div>
          </div>

          <!-- 看过但未评分 -->
          <div
            v-if="attention.unrated.length && (attentionFilter === 'all' || attentionFilter === 'unrated')"
            id="attention-unrated-list"
            class="rounded-3xl p-6 bg-white/[0.02] backdrop-blur-3xl border border-white/8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)] space-y-4"
          >
            <div class="flex items-center justify-between">
              <div>
                <h4 class="text-sm font-black text-white/90 flex items-center gap-2">
                  <Star :size="15" class="text-amber-400" />
                  看过但尚未评分的作品
                </h4>
                <p class="text-xs text-white/45 mt-0.5">鼠标直接在卡片底部星星上点击即可一键打分</p>
              </div>
              <span class="text-xs font-bold text-accent bg-accent/10 border border-accent/20 px-2.5 py-1 rounded-lg tabular-nums">
                待评分 {{ attention.unrated.length }} 部
              </span>
            </div>

            <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              <div
                v-for="item in attention.unrated"
                :key="item.id"
                class="rounded-2xl overflow-hidden bg-white/[0.02] border border-white/8 shadow-md group flex flex-col justify-between hover:bg-white/[0.05] hover:border-white/15 hover:-translate-y-1 transition-all duration-300"
              >
                <RouterLink :to="`/?media=${item.id}`" class="block flex-1">
                  <div class="aspect-[3/4] bg-black/40 overflow-hidden relative">
                    <img
                      v-if="item.cover_path"
                      :src="thumbnailUrl(item.cover_path)"
                      class="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      loading="lazy"
                      decoding="async"
                    />
                    <div v-else class="w-full h-full flex items-center justify-center text-white/20 text-xs">无封面</div>
                    <span
                      v-if="item.media_type"
                      class="absolute top-2 left-2 text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-black/70 backdrop-blur-md border border-white/10 text-white/80"
                    >
                      {{ typeMeta[item.media_type]?.label ?? item.media_type }}
                    </span>
                  </div>
                  <div class="p-3 pb-1">
                    <div class="text-xs text-white/85 font-bold line-clamp-2 leading-snug group-hover:text-accent transition-colors" :title="item.title">
                      {{ item.title }}
                    </div>
                  </div>
                </RouterLink>

                <!-- 一键星级打分条 -->
                <div class="px-3 pb-3 pt-1">
                  <div class="flex items-center justify-between pt-2 border-t border-white/5">
                    <div class="flex items-center gap-0.5" title="点击直接评星">
                      <button
                        v-for="s in 5"
                        :key="s"
                        type="button"
                        @click="quickRate(item, s, $event)"
                        @mouseenter="hoverStars[item.id] = s"
                        @mouseleave="delete hoverStars[item.id]"
                        class="p-0.5 text-white/25 hover:text-amber-400 transition-all hover:scale-110 active:scale-95 cursor-pointer"
                        :class="{ 'text-amber-400': (hoverStars[item.id] || item.rating) >= s }"
                      >
                        <Star :size="13" :fill="(hoverStars[item.id] || item.rating) >= s ? 'currentColor' : 'none'" />
                      </button>
                    </div>
                    <span class="text-[10px] text-white/35 font-semibold shrink-0">{{ lastOpenedText(item) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 尘封的高分作品 -->
          <div
            v-if="attention.dusty.length && (attentionFilter === 'all' || attentionFilter === 'dusty')"
            class="rounded-3xl p-6 bg-white/[0.02] backdrop-blur-3xl border border-white/8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)] space-y-4"
          >
            <div class="flex items-center justify-between">
              <div>
                <h4 class="text-sm font-black text-white/90 flex items-center gap-2">
                  <Sparkles :size="15" class="text-accent" />
                  尘封的高分作品 (评分 ≥ 4)
                </h4>
                <p class="text-xs text-white/45 mt-0.5">重温已被封存多日的好作 · 已超过 {{ attention.stale_days }} 天未打开</p>
              </div>
              <span class="text-xs font-bold text-white/50 bg-white/5 border border-white/10 px-2.5 py-1 rounded-lg tabular-nums">
                共 {{ attention.dusty.length }} 部
              </span>
            </div>

            <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              <RouterLink
                v-for="item in attention.dusty"
                :key="item.id"
                :to="`/?media=${item.id}`"
                class="rounded-2xl overflow-hidden bg-white/[0.02] border border-white/8 shadow-md group flex flex-col justify-between hover:bg-white/[0.05] hover:border-white/15 hover:-translate-y-1 transition-all duration-300"
              >
                <div class="aspect-[3/4] bg-black/40 overflow-hidden relative">
                  <img
                    v-if="item.cover_path"
                    :src="thumbnailUrl(item.cover_path)"
                    class="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    loading="lazy"
                    decoding="async"
                  />
                  <div v-else class="w-full h-full flex items-center justify-center text-white/20 text-xs">无封面</div>
                  <span
                    v-if="item.media_type"
                    class="absolute top-2 left-2 text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-black/70 backdrop-blur-md border border-white/10 text-white/80"
                  >
                    {{ typeMeta[item.media_type]?.label ?? item.media_type }}
                  </span>
                </div>
                <div class="p-3 flex-1 flex flex-col justify-between">
                  <div class="text-xs text-white/85 font-bold line-clamp-2 leading-snug group-hover:text-accent transition-colors" :title="item.title">
                    {{ item.title }}
                  </div>
                  <div class="flex items-center justify-between mt-2.5 pt-2 border-t border-white/5">
                    <span class="flex items-center gap-0.5 text-amber-300">
                      <Star v-for="n in item.rating" :key="n" :size="10" fill="currentColor" />
                    </span>
                    <span class="text-[10px] text-white/35 font-semibold">{{ lastOpenedText(item) }}</span>
                  </div>
                </div>
              </RouterLink>
            </div>
          </div>
        </div>

        <div
          v-else-if="attention"
          class="rounded-3xl p-8 bg-white/[0.02] backdrop-blur-3xl border border-white/8 text-center text-white/45 text-sm"
        >
          暂无待整理或未评分作品，媒体库井井有条 ✨
        </div>
      </section>
    </div>

    <!-- ==========================================
         全屏悬浮即时提示窗 (Heatmap & Growth Tooltips)
         ========================================== -->
    <!-- 1. 热力图浮窗 -->
    <Teleport to="body">
      <Transition name="tooltip-fade">
        <div
          v-if="heatmapTooltip.visible && heatmapTooltip.day"
          class="fixed z-[999] pointer-events-none -translate-x-1/2 -translate-y-full px-3.5 py-2.5 rounded-2xl bg-sidebar/95 backdrop-blur-2xl border border-white/20 shadow-2xl shadow-black/80 text-xs whitespace-nowrap transition-all duration-75"
          :style="{
            left: `${heatmapTooltip.x}px`,
            top: `${heatmapTooltip.y}px`,
          }"
        >
          <div class="flex items-center gap-2 mb-1.5">
            <span class="font-bold text-white/90 text-xs">{{ heatmapTooltip.day.formattedDate }}</span>
            <span class="text-white/40 text-[11px] font-semibold">{{ heatmapTooltip.day.dayName }}</span>
          </div>
          <div class="flex items-center gap-2 font-bold">
            <span
              class="w-2 h-2 rounded-full"
              :class="heatmapTooltip.day.count > 0 ? 'bg-accent shadow-[0_0_8px_rgba(var(--color-accent),0.8)]' : 'bg-white/20'"
            />
            <span :class="heatmapTooltip.day.count > 0 ? 'text-accent' : 'text-white/50'">
              {{ heatmapTooltip.day.count > 0 ? `打开 ${heatmapTooltip.day.count} 次` : '无媒体访问记录' }}
            </span>
            <span
              v-if="heatmapTooltip.day.level === 4"
              class="text-[10px] font-black px-1.5 py-0.5 rounded-md bg-accent/20 text-accent border border-accent/40"
            >
              🔥 活跃峰值
            </span>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 2. 增长趋势柱状图浮窗 -->
    <Teleport to="body">
      <Transition name="tooltip-fade">
        <div
          v-if="growthTooltip.visible && growthTooltip.point"
          class="fixed z-[999] pointer-events-none -translate-x-1/2 -translate-y-full px-4 py-3 rounded-2xl bg-sidebar/95 backdrop-blur-2xl border border-white/20 shadow-2xl shadow-black/80 text-xs whitespace-nowrap transition-all duration-75 min-w-[170px]"
          :style="{
            left: `${growthTooltip.x}px`,
            top: `${growthTooltip.y}px`,
          }"
        >
          <div class="font-bold text-white/90 text-sm mb-2 border-b border-white/10 pb-1.5 flex items-center justify-between">
            <span>{{ growthTooltip.point.fullLabel }}</span>
            <span
              v-if="growthTooltip.point.momChange"
              class="text-[10px] font-bold px-1.5 py-0.5 rounded"
              :class="growthTooltip.point.isPositiveMom ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'"
            >
              {{ growthTooltip.point.momChange }}
            </span>
          </div>
          <div class="space-y-1 text-white/75 font-semibold">
            <div class="flex items-center justify-between gap-3">
              <span class="text-white/45">当月新增：</span>
              <span class="font-bold text-accent font-mono">+{{ growthTooltip.point.added.toLocaleString() }} 部</span>
            </div>
            <div class="flex items-center justify-between gap-3">
              <span class="text-white/45">全库占比：</span>
              <span class="font-bold font-mono">{{ growthTooltip.point.pctOfTotal }}%</span>
            </div>
            <div class="flex items-center justify-between gap-3">
              <span class="text-white/45">截止累计：</span>
              <span class="font-bold text-white font-mono">{{ growthTooltip.point.cumulative.toLocaleString() }} 部</span>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 3. 星级打分 Toast -->
    <Teleport to="body">
      <Transition name="tooltip-fade">
        <div
          v-if="rateToast"
          class="fixed bottom-6 right-6 z-[300] flex items-center gap-2.5 rounded-2xl border border-amber-400/40 bg-sidebar/95 px-5 py-3 text-sm font-bold text-white shadow-2xl backdrop-blur-xl"
        >
          <Star class="text-amber-400 shrink-0" :size="18" fill="currentColor" />
          <span>{{ rateToast }}</span>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.tooltip-fade-enter-active,
.tooltip-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.tooltip-fade-enter-from,
.tooltip-fade-leave-to {
  opacity: 0;
  transform: translate(-50%, -90%) scale(0.96);
}
</style>
