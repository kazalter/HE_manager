<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import axios from 'axios'
import {
  AlertTriangle,
  ArrowDown,
  Clock,
  Eye,
  HardDrive,
  Layers,
  RefreshCw,
  Sparkles,
  Star,
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
import { EmptyState, PageHeader, SectionHeader, UiButton, UiCard, UiChip, UiSegmented, UiSkeleton } from '../components/ui'

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
  { id: 'section-overview', label: '概览指标', short: '概览' },
  { id: 'section-distribution', label: '资产分布', short: '分布' },
  { id: 'section-growth', label: '入库趋势', short: '趋势' },
  { id: 'section-activity', label: '活跃轨迹', short: '活跃' },
  { id: 'section-attention', label: '整理与亮点', short: '整理' },
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
  resizeObserver?.disconnect()
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
    nextTick(() => {
      initObserver()
      observeChartSizes()
    })
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

const typeMeta: Record<string, { label: string }> = {
  video: { label: '视频' },
  manga: { label: '漫画' },
  image: { label: '杂图' },
  audio: { label: '音频' },
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
  const videoHours = Math.floor(videoSec / 3600)

  const avgSizeBytes = total > 0 ? Math.round(o.total_size_bytes / total) : 0

  return [
    {
      label: '媒体总数',
      value: total.toLocaleString(),
      unit: '项',
      icon: Layers,
      detail: `视频 ${(o.by_type['video'] || 0).toLocaleString()} · 漫画 ${(o.by_type['manga'] || 0).toLocaleString()}`,
      sub: `杂图 ${(o.by_type['image'] || 0).toLocaleString()} · 音频 ${(o.by_type['audio'] || 0).toLocaleString()}`,
      to: '/',
    },
    {
      label: '存储总体积',
      value: formatSize(o.total_size_bytes),
      unit: '',
      icon: HardDrive,
      detail: `单项均重约 ${formatSize(avgSizeBytes)}`,
      sub: '',
      to: null,
    },
    {
      label: '观看完成度',
      value: `${viewedPct}%`,
      unit: '',
      icon: Eye,
      detail: `已看 ${viewed.toLocaleString()} / ${total.toLocaleString()}`,
      sub: `在看 ${(o.view_status['viewing'] || 0).toLocaleString()} · 未看 ${(o.view_status['unviewed'] || 0).toLocaleString()}`,
      to: null,
    },
    {
      label: '视频总时长',
      value: videoHours > 0 ? videoHours.toLocaleString() : formatDurationHours(videoSec),
      unit: videoHours > 0 ? '小时' : '',
      icon: Clock,
      detail: `合计 ${formatDurationHours(videoSec)}`,
      sub: `均片长约 ${avgVideoMin} 分钟`,
      to: '/type/video',
    },
    {
      label: '特别收藏',
      value: o.favorites.toLocaleString(),
      unit: '部',
      icon: Star,
      detail: total > 0 ? `收藏率 ${((o.favorites / total) * 100).toFixed(1)}%` : '暂无收藏',
      sub: '',
      to: '/?favorite=true',
    },
    {
      label: '评分覆盖率',
      value: o.rated > 0 ? `${((o.rated / total) * 100).toFixed(1)}%` : '0%',
      unit: '',
      icon: Sparkles,
      detail: `已评 ${o.rated.toLocaleString()} 部`,
      sub: o.rated > 0 ? `平均 ${o.average_rating ? o.average_rating.toFixed(2) : '—'} 星` : '打分可激发智能推荐',
      to: null,
    },
  ]
})

// ---- Donut Charts ----
// One restrained ramp for every chart: the theme accent, then neutral steps.
// Slices are coloured by rank (largest first), so no per-type rainbow.
const SERIES_COLORS = [
  'rgb(var(--color-accent))',
  'rgb(var(--color-accent) / 0.5)',
  'rgb(var(--color-muted) / 0.7)',
  'rgb(var(--color-subtle) / 0.45)',
  'rgb(var(--color-line-strong))',
]
const seriesColor = (index: number) => SERIES_COLORS[Math.min(index, SERIES_COLORS.length - 1)]!

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
  const visible = entries.filter((e) => e.count > 0).sort((a, b) => b.count - a.count)
  const total = visible.reduce((s, e) => s + e.count, 0)
  const C = DONUT_CIRCUMFERENCE
  let cumulative = 0
  const slices: DonutSlice[] = visible.map((e, index) => {
    const ratio = total > 0 ? e.count / total : 0
    const len = ratio * C
    const slice: DonutSlice = {
      ...e,
      color: seriesColor(index),
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
  const rank = [...order].sort((a, b) => (o.by_type_size[b] || 0) - (o.by_type_size[a] || 0))
  return order
    .map((key) => {
      const size = o.by_type_size[key] || 0
      const count = o.by_type[key] || 0
      const pct = ((size / o.total_size_bytes) * 100).toFixed(1)
      const avg = count > 0 ? formatSize(Math.round(size / count)) : '—'
      return {
        key,
        label: typeMeta[key]?.label ?? key,
        color: seriesColor(rank.indexOf(key)),
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
  showLabel: boolean
  barX: number
  barY: number
  barW: number
  barH: number
  lineY: number
}

// The chart's viewBox follows the container's pixel size, so text and bars keep
// their real size on phones instead of being scaled down with the SVG.
const growthChartEl = ref<HTMLElement | null>(null)
const heatmapEl = ref<HTMLElement | null>(null)
const chartWidth = ref(800)
const heatmapWidth = ref(800)
const SVG_H = 260
const PAD_T = 28
const PAD_B = 32
const PLOT_H = SVG_H - PAD_T - PAD_B
const SVG_W = computed(() => Math.max(280, chartWidth.value))
const PAD_L = computed(() => (SVG_W.value < 520 ? 40 : 52))
const PAD_R = 12
const PLOT_W = computed(() => SVG_W.value - PAD_L.value - PAD_R)

let resizeObserver: ResizeObserver | null = null
const observeChartSizes = () => {
  if (typeof ResizeObserver === 'undefined') return
  resizeObserver?.disconnect()
  resizeObserver = new ResizeObserver(() => {
    if (growthChartEl.value) chartWidth.value = Math.round(growthChartEl.value.clientWidth)
    if (heatmapEl.value) heatmapWidth.value = Math.round(heatmapEl.value.clientWidth)
  })
  if (growthChartEl.value) resizeObserver.observe(growthChartEl.value)
  if (heatmapEl.value) resizeObserver.observe(heatmapEl.value)
}

const growthData = computed(() => {
  const g = distribution.value?.growth ?? []
  if (g.length === 0) return null

  const totalAdded = g.reduce((sum, item) => sum + item.added, 0)
  const maxAdded = Math.max(1, ...g.map((p) => p.added))
  const maxCum = Math.max(1, ...g.map((p) => p.cumulative))
  const slotW = PLOT_W.value / g.length
  const barW = Math.max(6, Math.min(40, slotW * 0.56))
  // Thin out labels when months get narrow (phones).
  const labelEvery = slotW >= 44 ? 1 : slotW >= 24 ? 2 : 3
  const showBarValues = slotW >= 40

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
    const cx = PAD_L.value + i * slotW + slotW / 2
    const slotX = PAD_L.value + i * slotW
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
      showLabel: (g.length - 1 - i) % labelEvery === 0,
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
    showBarValues,
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
    y: Math.round(rect.top + 4),
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

// Cells grow to fill wide screens; phones keep a 12 px floor and scroll.
const HEATMAP_GAP = 3
const HEATMAP_LABEL_W = 32
const heatmapCell = computed(() => {
  const weeks = heatmap.value?.weeks.length || 53
  const fit = Math.floor((heatmapWidth.value - HEATMAP_LABEL_W) / weeks) - HEATMAP_GAP
  return Math.max(12, Math.min(18, fit))
})
const heatmapStep = computed(() => heatmapCell.value + HEATMAP_GAP)

// Show the most recent weeks first when the grid has to scroll.
watch([heatmap, heatmapCell], () => nextTick(() => {
  if (heatmapEl.value) heatmapEl.value.scrollLeft = heatmapEl.value.scrollWidth
}))

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

const LEVEL_CLASSES = ['bg-surface-3', 'bg-accent/25', 'bg-accent/50', 'bg-accent/75', 'bg-accent']
const levelClass = (lvl: number, inRange: boolean) => (inRange ? LEVEL_CLASSES[lvl] : 'bg-transparent')

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
    y: Math.round(rect.top),
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
const growthModeOptions = [
  { value: 'both' as const, label: '柱 + 线' },
  { value: 'monthly' as const, label: '月度新增' },
  { value: 'cumulative' as const, label: '累计总量' },
]
const attentionOptions = computed(() => {
  const at = attention.value
  const out: { value: 'all' | 'unrated' | 'dusty'; label: string }[] = [{ value: 'all', label: '全部' }]
  if (at?.unrated.length) out.push({ value: 'unrated', label: `已看未评 ${at.unrated.length}` })
  if (at?.dusty.length) out.push({ value: 'dusty', label: `尘封高分 ${at.dusty.length}` })
  return out
})
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
    rateToast.value = `已为《${item.title}》评分 ${stars} 星`
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
  <div class="min-h-full">
    <PageHeader title="数据看板">
      <template #description>
        <span>媒体库资产、存储、入库增长与活跃轨迹</span>
        <span v-if="lastUpdatedTime" class="whitespace-nowrap tabular-nums"><span class="mx-1.5 text-faint" aria-hidden="true">·</span>更新于 {{ lastUpdatedTime }}</span>
      </template>
      <template #actions>
        <UiButton variant="secondary" class="pointer-coarse:h-11" title="刷新全部统计数据" @click="refresh">
          <template #icon><RefreshCw :size="16" :class="{ 'animate-spin': refreshSpinning }" /></template>
          刷新
        </UiButton>
      </template>
    </PageHeader>

    <!-- 吸顶分区导航 -->
    <nav
      v-if="!loading && !errorMessage"
      aria-label="看板分区"
      class="page-gutter sticky top-0 z-20 -mt-2 border-b border-line bg-background/95 py-2 lg:-mt-3"
    >
      <div class="page-container">
        <div class="flex w-full gap-0.5 rounded-lg border border-line bg-surface p-0.5 sm:inline-flex sm:w-auto">
          <button
            v-for="item in navSections"
            :key="item.id"
            type="button"
            :aria-current="activeSection === item.id ? 'true' : undefined"
            class="h-8 flex-1 whitespace-nowrap rounded-md px-3 text-meta font-medium transition-colors duration-150 focus-ring sm:flex-none pointer-coarse:h-10"
            :class="activeSection === item.id ? 'bg-surface-3 text-ink shadow-[0_1px_2px_rgb(0_0_0/0.35)]' : 'text-subtle hover:text-ink'"
            @click="scrollToSection(item.id)"
          >
            <span class="sm:hidden">{{ item.short }}</span>
            <span class="hidden sm:inline">{{ item.label }}</span>
          </button>
        </div>
      </div>
    </nav>

    <div class="page-gutter pt-6 pb-12">
      <div class="page-container">
        <!-- 加载与错误状态 -->
        <div v-if="loading" class="space-y-10" aria-busy="true" aria-label="正在汇总媒体库统计">
          <div class="grid grid-cols-2 gap-3 md:grid-cols-3 lg:gap-4 2xl:grid-cols-6">
            <UiCard v-for="n in 6" :key="n" padding="md">
              <UiSkeleton shape="text" class="w-1/2" />
              <UiSkeleton class="mt-3 h-7 w-2/3 rounded-md" />
              <UiSkeleton shape="text" class="mt-3 w-4/5" />
            </UiCard>
          </div>
          <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <UiSkeleton v-for="n in 3" :key="n" class="h-48 w-full rounded-2xl" />
          </div>
        </div>

        <UiCard v-else-if="errorMessage" padding="none">
          <EmptyState tone="danger" :icon="AlertTriangle" title="加载统计数据失败" :description="errorMessage">
            <UiButton variant="secondary" size="sm" @click="refresh"><template #icon><RefreshCw :size="14" /></template>重试</UiButton>
          </EmptyState>
        </UiCard>

        <!-- 主内容区 -->
        <div v-else class="space-y-12">
          <!-- 1. 概览指标 -->
          <section id="section-overview" class="scroll-mt-16">
            <SectionHeader title="核心概览" description="点击可跳转的卡片进入对应分类" />
            <div class="grid grid-cols-2 gap-3 md:grid-cols-3 lg:gap-4 2xl:grid-cols-6">
              <component
                :is="card.to ? RouterLink : 'div'"
                v-for="card in overviewCards"
                :key="card.label"
                :to="card.to ?? undefined"
                class="group flex min-w-0 flex-col rounded-2xl border border-line bg-surface p-4 sm:p-5"
                :class="card.to ? 'transition-colors duration-150 hover:border-line-strong hover:bg-surface-2 focus-ring' : ''"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="truncate text-meta text-subtle">{{ card.label }}</span>
                  <component :is="card.icon" :size="16" class="shrink-0 text-subtle transition-colors group-hover:text-muted" aria-hidden="true" />
                </div>
                <p class="mt-1.5 flex min-w-0 items-baseline gap-1 whitespace-nowrap">
                  <span class="truncate text-title font-semibold text-ink tabular-nums">{{ card.value }}</span>
                  <span v-if="card.unit" class="shrink-0 text-meta text-subtle">{{ card.unit }}</span>
                </p>
                <p class="mt-1 truncate text-caption text-muted tabular-nums" :title="card.detail">{{ card.detail }}</p>
                <p v-if="card.sub" class="mt-0.5 truncate text-caption text-subtle tabular-nums" :title="card.sub">{{ card.sub }}</p>
              </component>
            </div>
          </section>

          <!-- 2. 资产分布 -->
          <section id="section-distribution" class="scroll-mt-16">
            <SectionHeader title="资产结构" description="悬停扇区或图例查看明细" />
            <div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:gap-4 xl:grid-cols-3">
              <UiCard v-for="card in donutCards" :key="card.id" padding="md">
                <div class="mb-4 flex items-center justify-between gap-2">
                  <h3 class="text-body font-medium text-ink">{{ card.title }}</h3>
                  <span class="text-caption text-subtle tabular-nums">{{ card.donut.slices.length }} 项</span>
                </div>
                <div class="flex items-center gap-5">
                  <div class="relative size-28 shrink-0 sm:size-32">
                    <svg viewBox="0 0 100 100" class="h-full w-full -rotate-90" aria-hidden="true">
                      <circle cx="50" cy="50" r="40" fill="none" stroke="rgb(var(--color-surface-3))" stroke-width="12" />
                      <circle
                        v-for="s in card.donut.slices"
                        :key="s.key"
                        cx="50"
                        cy="50"
                        r="40"
                        fill="none"
                        stroke-linecap="butt"
                        :stroke="s.color"
                        :stroke-width="hoveredDonutSlice[card.id]?.key === s.key ? 15 : 12"
                        :stroke-dasharray="s.dasharray"
                        :stroke-dashoffset="s.dashoffset"
                        :opacity="hoveredDonutSlice[card.id] && hoveredDonutSlice[card.id]?.key !== s.key ? 0.45 : 1"
                        class="cursor-pointer transition-opacity duration-150"
                        @mouseenter="setDonutHover(card.id, s)"
                        @mouseleave="setDonutHover(card.id, null)"
                      />
                    </svg>
                    <div class="pointer-events-none absolute inset-0 flex flex-col items-center justify-center p-3 text-center">
                      <template v-if="hoveredDonutSlice[card.id]">
                        <span class="max-w-full truncate text-heading font-semibold leading-none text-ink tabular-nums">
                          {{ hoveredDonutSlice[card.id]?.valueLabel ?? hoveredDonutSlice[card.id]?.count.toLocaleString() }}
                        </span>
                        <span class="mt-1 max-w-full truncate text-caption text-subtle tabular-nums">
                          {{ hoveredDonutSlice[card.id]?.label }} {{ hoveredDonutSlice[card.id]?.pct }}%
                        </span>
                      </template>
                      <template v-else>
                        <span class="max-w-full truncate text-heading font-semibold leading-none text-ink tabular-nums">{{ card.donut.totalLabel }}</span>
                        <span class="mt-1 text-caption text-subtle">{{ card.centerLabel }}</span>
                      </template>
                    </div>
                  </div>

                  <ul class="min-w-0 flex-1 space-y-0.5">
                    <li
                      v-for="s in card.donut.slices"
                      :key="s.key"
                      @mouseenter="setDonutHover(card.id, s)"
                      @mouseleave="setDonutHover(card.id, null)"
                    >
                      <component
                        :is="s.to ? RouterLink : 'div'"
                        :to="s.to ?? undefined"
                        class="flex min-h-8 items-center gap-2 rounded-lg px-2 text-meta transition-colors duration-150"
                        :class="[hoveredDonutSlice[card.id]?.key === s.key ? 'bg-surface-2' : '', s.to ? 'hover:bg-surface-2 focus-ring-inset' : '']"
                      >
                        <span class="size-2.5 shrink-0 rounded-sm" :style="{ backgroundColor: s.color }" aria-hidden="true" />
                        <span class="min-w-0 truncate text-muted">{{ s.label }}</span>
                        <span class="ml-auto shrink-0 text-ink tabular-nums">{{ s.valueLabel ?? s.count.toLocaleString() }}</span>
                        <span class="w-9 shrink-0 text-right text-caption text-subtle tabular-nums">{{ s.pct }}%</span>
                      </component>
                    </li>
                  </ul>
                </div>
              </UiCard>
            </div>

            <!-- 存储空间 -->
            <UiCard v-if="storageBreakdown.length" padding="md" class="mt-3 lg:mt-4">
              <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <h3 class="text-body font-medium text-ink">存储占用与单项均重</h3>
                <span class="text-meta text-subtle tabular-nums">全库共 {{ formatSize(overview?.total_size_bytes || 0) }}</span>
              </div>
              <div class="mt-4 flex h-2 gap-0.5 overflow-hidden rounded-sm bg-surface-3" aria-hidden="true">
                <div
                  v-for="item in storageBreakdown"
                  :key="item.key"
                  class="h-full"
                  :style="{ width: `${item.pct}%`, backgroundColor: item.color }"
                  :title="`${item.label}: ${item.sizeFormatted} (${item.pctFormatted})`"
                />
              </div>
              <div class="-mx-2 mt-3 grid grid-cols-2 md:grid-cols-4">
                <RouterLink
                  v-for="item in storageBreakdown"
                  :key="item.key"
                  :to="item.to"
                  class="group rounded-lg p-2 transition-colors duration-150 hover:bg-surface-2 focus-ring sm:p-3"
                >
                  <div class="flex items-center gap-2 text-meta">
                    <span class="size-2.5 shrink-0 rounded-sm" :style="{ backgroundColor: item.color }" aria-hidden="true" />
                    <span class="text-muted">{{ item.label }}</span>
                    <span class="ml-auto text-caption text-subtle tabular-nums">{{ item.pctFormatted }}</span>
                  </div>
                  <p class="mt-1 text-heading font-semibold text-ink tabular-nums">{{ item.sizeFormatted }}</p>
                  <p class="mt-0.5 truncate text-caption text-subtle tabular-nums">{{ item.count.toLocaleString() }} 项 · 均重 {{ item.avgSize }}</p>
                </RouterLink>
              </div>
            </UiCard>
          </section>

          <!-- 3. 入库增长趋势 -->
          <section id="section-growth" class="scroll-mt-16">
            <SectionHeader title="入库趋势">
              <template #actions>
                <UiSegmented v-model="growthChartMode" label="图表模式" size="sm" :options="growthModeOptions" />
              </template>
            </SectionHeader>

            <UiCard padding="none">
              <div v-if="growthData" class="grid grid-cols-2 border-b border-line md:grid-cols-4">
                <div class="border-b border-line p-4 sm:px-5 md:border-b-0">
                  <p class="text-meta text-subtle">历史入库总量</p>
                  <p class="mt-1 text-heading font-semibold text-ink tabular-nums">{{ growthData.totalAdded.toLocaleString() }}<span class="ml-1 text-meta font-normal text-subtle">部</span></p>
                </div>
                <div class="border-b border-l border-line p-4 sm:px-5 md:border-b-0">
                  <p class="text-meta text-subtle">最高单月新增</p>
                  <p class="mt-1 text-heading font-semibold text-ink tabular-nums">{{ growthData.maxMonth.added.toLocaleString() }}</p>
                  <p class="text-caption text-subtle tabular-nums">{{ growthData.maxMonth.fullLabel }}</p>
                </div>
                <div class="p-4 sm:px-5 md:border-l md:border-line">
                  <p class="text-meta text-subtle">近 3 个月月均</p>
                  <p class="mt-1 text-heading font-semibold text-ink tabular-nums">{{ growthData.avgRecent3 }}<span class="ml-1 text-meta font-normal text-subtle">部/月</span></p>
                </div>
                <div class="border-l border-line p-4 sm:px-5">
                  <p class="text-meta text-subtle">最新月份入库</p>
                  <p class="mt-1 text-heading font-semibold text-ink tabular-nums">+{{ growthData.latestMonth.added.toLocaleString() }}</p>
                  <p class="text-caption text-subtle tabular-nums">{{ growthData.latestMonth.fullLabel }}</p>
                </div>
              </div>

              <div v-if="growthData" class="p-4 sm:p-5">
                <div ref="growthChartEl" class="relative w-full">
                  <svg
                    :viewBox="`0 0 ${SVG_W} ${SVG_H}`"
                    :width="SVG_W"
                    :height="SVG_H"
                    class="block max-w-full overflow-visible select-none"
                    role="img"
                    :aria-label="`入库趋势：共 ${growthData.monthsCount} 个月，历史入库 ${growthData.totalAdded} 部`"
                  >
                    <!-- 参考网格线 -->
                    <g>
                      <template v-for="(tick, idx) in growthData.yTicks" :key="idx">
                        <line :x1="PAD_L" :y1="tick.y" :x2="SVG_W - PAD_R" :y2="tick.y" stroke="rgb(var(--color-line))" stroke-width="1" />
                        <text :x="PAD_L - 8" :y="tick.y + 4" text-anchor="end" class="fill-subtle text-caption tabular-nums">{{ tick.label }}</text>
                      </template>
                    </g>

                    <!-- 柱子与悬停槽位 -->
                    <g>
                      <template v-for="p in growthData.points" :key="p.month">
                        <rect
                          :x="p.slotX"
                          :y="PAD_T"
                          :width="p.slotW"
                          :height="PLOT_H"
                          :fill="hoveredGrowthIndex === p.index ? 'rgb(var(--color-surface-2))' : 'transparent'"
                          rx="6"
                          class="cursor-pointer"
                          @mouseenter="onGrowthSlotEnter(p, $event)"
                          @mouseleave="onGrowthSlotLeave"
                        />
                        <rect
                          :x="p.barX"
                          :y="p.barY"
                          :width="p.barW"
                          :height="Math.max(0, p.barH)"
                          rx="3"
                          class="pointer-events-none transition-[fill] duration-150"
                          :fill="hoveredGrowthIndex === p.index ? 'rgb(var(--color-accent))' : growthChartMode === 'both' ? 'rgb(var(--color-accent) / 0.45)' : 'rgb(var(--color-accent) / 0.7)'"
                        />
                        <text
                          v-if="growthData.showBarValues || hoveredGrowthIndex === p.index"
                          :x="p.cx"
                          :y="p.barY - 6"
                          text-anchor="middle"
                          class="pointer-events-none text-caption tabular-nums"
                          :class="hoveredGrowthIndex === p.index ? 'fill-ink' : 'fill-subtle'"
                        >{{ (growthChartMode === 'cumulative' ? p.cumulative : p.added).toLocaleString() }}</text>
                        <text
                          v-if="p.showLabel || hoveredGrowthIndex === p.index"
                          :x="p.cx"
                          :y="SVG_H - 10"
                          text-anchor="middle"
                          class="pointer-events-none text-caption"
                          :class="hoveredGrowthIndex === p.index ? 'fill-ink' : 'fill-subtle'"
                        >{{ p.monthShort }}</text>
                      </template>
                    </g>

                    <!-- 累计折线 -->
                    <template v-if="growthChartMode !== 'monthly' && growthData.linePoints">
                      <polyline
                        :points="growthData.linePoints"
                        fill="none"
                        stroke="rgb(var(--color-accent-glow))"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        class="pointer-events-none"
                      />
                      <circle
                        v-for="p in growthData.points"
                        :key="'dot-' + p.month"
                        :cx="p.cx"
                        :cy="p.lineY"
                        :r="hoveredGrowthIndex === p.index ? 4.5 : 3"
                        fill="rgb(var(--color-surface))"
                        stroke="rgb(var(--color-accent-glow))"
                        stroke-width="2"
                        class="pointer-events-none"
                      />
                    </template>
                  </svg>
                </div>

                <div class="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-line pt-3 text-caption text-subtle">
                  <div class="flex items-center gap-4">
                    <span class="flex items-center gap-1.5">
                      <span class="size-2.5 rounded-sm bg-accent/70" aria-hidden="true" />
                      {{ growthChartMode === 'cumulative' ? '当月累计体量' : '当月入库新增' }}
                    </span>
                    <span v-if="growthChartMode === 'both'" class="flex items-center gap-1.5">
                      <span class="h-0.5 w-3 rounded-sm bg-accent-glow" aria-hidden="true" />
                      累计全库总量
                    </span>
                  </div>
                  <span class="tabular-nums">共 {{ growthData.monthsCount }} 个月</span>
                </div>
              </div>

              <EmptyState v-else compact title="暂无入库时间跨度数据" />
            </UiCard>
          </section>

          <!-- 4. 活跃热力图 -->
          <section id="section-activity" class="scroll-mt-16">
            <SectionHeader title="近一年活跃轨迹" />
            <div class="scrollbar-none -mx-4 mb-3 flex gap-2 overflow-x-auto px-4 sm:-mx-6 sm:px-6 lg:mx-0 lg:px-0" role="group" aria-label="按类型筛选">
              <UiChip
                v-for="tab in heatmapTypeTabs"
                :key="tab.key"
                :selected="heatmapType === tab.key"
                :count="tab.total.toLocaleString()"
                @click="heatmapType = tab.key"
              >{{ tab.label }}</UiChip>
            </div>

            <UiCard padding="none">
              <div v-if="heatmap" class="grid grid-cols-3 border-b border-line">
                <div class="p-4 sm:px-5">
                  <p class="text-meta text-subtle">打开总量</p>
                  <p class="mt-1 text-heading font-semibold text-ink tabular-nums">{{ heatmap.total.toLocaleString() }}<span class="ml-1 text-meta font-normal text-subtle">次</span></p>
                </div>
                <div class="border-l border-line p-4 sm:px-5">
                  <p class="text-meta text-subtle">活跃天数</p>
                  <p class="mt-1 text-heading font-semibold text-ink tabular-nums">{{ heatmap.activeDays }}<span class="ml-1 text-meta font-normal text-subtle">天</span></p>
                  <p class="text-caption text-subtle tabular-nums">占全年 {{ heatmap.activePct }}%</p>
                </div>
                <div class="border-l border-line p-4 sm:px-5">
                  <p class="text-meta text-subtle">单日峰值</p>
                  <p class="mt-1 text-heading font-semibold text-ink tabular-nums">{{ heatmap.max }}<span class="ml-1 text-meta font-normal text-subtle">次</span></p>
                </div>
              </div>

              <div class="p-4 sm:p-5">
                <div v-if="heatmap" ref="heatmapEl" class="overflow-x-auto pb-2 select-none">
                  <div class="inline-block min-w-max">
                    <div class="pointer-events-none relative mb-1.5 h-5" :style="{ marginLeft: `${HEATMAP_LABEL_W}px` }">
                      <span
                        v-for="m in monthHeaders"
                        :key="m.weekIndex"
                        class="absolute whitespace-nowrap text-caption text-subtle"
                        :style="{ left: `${m.weekIndex * heatmapStep}px` }"
                      >{{ m.label }}</span>
                    </div>
                    <div class="flex items-start">
                      <div class="flex shrink-0 flex-col pr-2 text-right text-caption text-subtle" :style="{ width: `${HEATMAP_LABEL_W}px`, gap: `${HEATMAP_GAP}px` }" aria-hidden="true">
                        <span v-for="(label, idx) in weekDayLabels" :key="idx" class="whitespace-nowrap" :style="{ height: `${heatmapCell}px`, lineHeight: `${heatmapCell}px` }">{{ label }}</span>
                      </div>
                      <div class="flex" :style="{ gap: `${HEATMAP_GAP}px` }">
                        <div v-for="(week, wi) in heatmap.weeks" :key="wi" class="flex flex-col" :style="{ gap: `${HEATMAP_GAP}px` }">
                          <div
                            v-for="day in week"
                            :key="day.date"
                            class="rounded-sm"
                            :class="[levelClass(day.level, day.inRange), day.inRange ? 'cursor-pointer hover:outline-2 hover:outline-offset-1 hover:outline-ink/70' : 'pointer-events-none']"
                            :style="{ width: `${heatmapCell}px`, height: `${heatmapCell}px` }"
                            @mouseenter="onHeatmapCellEnter(day, $event)"
                            @mouseleave="onHeatmapCellLeave"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-caption text-subtle">
                  <span class="pointer-coarse:hidden">悬停方格查看当天打开次数</span>
                  <div class="ml-auto flex items-center gap-1.5" aria-hidden="true">
                    <span>少</span>
                    <span v-for="cls in LEVEL_CLASSES" :key="cls" class="size-3 rounded-sm" :class="cls" />
                    <span>多</span>
                  </div>
                </div>
              </div>
            </UiCard>
          </section>

          <!-- 5. 重点整理与库亮点 -->
          <section id="section-attention" class="scroll-mt-16 space-y-10">
            <div>
              <SectionHeader title="库亮点" />
              <div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:gap-4 xl:grid-cols-3">
                <!-- Top 创作者 -->
                <UiCard v-if="highlights?.top_creators?.length" padding="none">
                  <div class="px-4 pt-4 pb-2 sm:px-5">
                    <h3 class="text-body font-medium text-ink">热门创作者</h3>
                    <p class="mt-0.5 text-meta text-subtle">按入库作品数排行</p>
                  </div>
                  <ol class="px-2 pb-2">
                    <li v-for="(c, idx) in highlights.top_creators.slice(0, 5)" :key="c.key">
                      <component
                        :is="creatorLink(c) ? RouterLink : 'div'"
                        :to="creatorLink(c) ?? undefined"
                        class="flex min-h-14 items-center gap-3 rounded-lg px-2 py-2"
                        :class="creatorLink(c) ? 'transition-colors duration-150 hover:bg-surface-2 focus-ring-inset' : ''"
                      >
                        <span class="w-4 shrink-0 text-center text-meta text-subtle tabular-nums">{{ idx + 1 }}</span>
                        <span class="size-10 shrink-0 overflow-hidden rounded-full bg-surface-2">
                          <img v-if="c.cover_path" :src="thumbnailUrl(c.cover_path)" alt="" class="h-full w-full object-cover" loading="eager" decoding="async" />
                        </span>
                        <span class="min-w-0 flex-1">
                          <span class="block truncate text-body font-medium text-ink" :title="c.display_name">{{ c.display_name }}</span>
                          <span class="mt-0.5 block text-caption text-subtle">{{ c.kind === 'x' ? 'X 创作者' : '漫画作者' }}</span>
                        </span>
                        <span class="shrink-0 text-meta text-muted tabular-nums">{{ c.media_count.toLocaleString() }} 部</span>
                      </component>
                    </li>
                  </ol>
                </UiCard>

                <!-- 最长视频 -->
                <UiCard v-if="highlights?.top_videos?.length" padding="none">
                  <div class="px-4 pt-4 pb-2 sm:px-5">
                    <h3 class="text-body font-medium text-ink">最长视频</h3>
                    <p class="mt-0.5 text-meta text-subtle">按播放时长排行</p>
                  </div>
                  <ol class="px-2 pb-2">
                    <li v-for="(v, idx) in highlights.top_videos.slice(0, 5)" :key="v.id">
                      <RouterLink :to="`/?media=${v.id}`" class="flex min-h-14 items-center gap-3 rounded-lg px-2 py-2 transition-colors duration-150 hover:bg-surface-2 focus-ring-inset">
                        <span class="w-4 shrink-0 text-center text-meta text-subtle tabular-nums">{{ idx + 1 }}</span>
                        <span class="relative h-9 w-16 shrink-0 overflow-hidden rounded-lg bg-surface-2">
                          <img v-if="v.cover_path" :src="thumbnailUrl(v.cover_path)" alt="" class="h-full w-full object-cover" loading="eager" decoding="async" />
                        </span>
                        <span class="min-w-0 flex-1">
                          <span class="block truncate text-body font-medium text-ink" :title="v.title">{{ v.title }}</span>
                          <span class="mt-0.5 block text-caption text-subtle tabular-nums">{{ formatSize(v.file_size) }}</span>
                        </span>
                        <span class="shrink-0 text-meta text-muted tabular-nums">{{ formatDurationShort(v.duration) }}</span>
                      </RouterLink>
                    </li>
                  </ol>
                </UiCard>

                <!-- 评分分布 -->
                <UiCard padding="md" class="md:col-span-2 xl:col-span-1">
                  <h3 class="text-body font-medium text-ink">评分分布</h3>
                  <p class="mt-0.5 text-meta text-subtle">按 1–5 星统计</p>
                  <div v-if="hasRatings" class="mt-4 space-y-2.5">
                    <div v-for="r in ratingBars" :key="r.stars" class="flex items-center gap-3">
                      <span class="flex w-16 shrink-0 items-center gap-1 text-meta text-muted tabular-nums">
                        <template v-if="r.stars > 0"><Star :size="13" class="text-star" fill="currentColor" aria-hidden="true" />{{ r.stars }} 星</template>
                        <template v-else>未打分</template>
                      </span>
                      <div class="h-2 flex-1 overflow-hidden rounded-sm bg-surface-3">
                        <div class="h-full rounded-sm" :class="r.stars > 0 ? 'bg-star/80' : 'bg-subtle/50'" :style="{ width: `${r.pct}%` }" />
                      </div>
                      <span class="w-12 shrink-0 text-right text-meta text-ink tabular-nums">{{ r.count.toLocaleString() }}</span>
                    </div>
                  </div>
                  <div v-else class="mt-4 rounded-lg bg-surface-2 px-4 py-6 text-center">
                    <p class="text-body font-medium text-ink">目前全库尚未评星</p>
                    <p class="mt-1 text-meta text-subtle">为已看过的作品评星，能让个性化推荐更加精准。</p>
                    <UiButton as="a" href="#attention-unrated-list" variant="secondary" size="sm" class="mt-4">
                      <template #icon><ArrowDown :size="14" /></template>去下方打分
                    </UiButton>
                  </div>
                </UiCard>
              </div>
            </div>

            <!-- 待整理清单 -->
            <div v-if="attention && (attention.unrated.length || attention.dusty.length)" class="space-y-10">
              <div>
                <SectionHeader title="待整理">
                  <template #actions>
                    <UiSegmented v-if="attentionOptions.length > 2" v-model="attentionFilter" label="待整理筛选" size="sm" :options="attentionOptions" />
                  </template>
                </SectionHeader>

                <div class="space-y-10">
                  <!-- 看过但未评分 -->
                  <div v-if="attention.unrated.length && (attentionFilter === 'all' || attentionFilter === 'unrated')" id="attention-unrated-list" class="scroll-mt-16">
                    <div class="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                      <h3 class="flex items-center gap-2 text-body font-medium text-ink">看过但尚未评分<span class="text-meta font-normal text-subtle tabular-nums">{{ attention.unrated.length }} 部</span></h3>
                      <p class="text-meta text-subtle">点击卡片下方的星星直接打分</p>
                    </div>
                    <div class="poster-grid">
                      <div v-for="item in attention.unrated" :key="item.id" class="group flex min-w-0 flex-col">
                        <RouterLink :to="`/?media=${item.id}`" class="block rounded-2xl focus-ring">
                          <div class="relative aspect-[3/4] overflow-hidden rounded-2xl bg-surface-2">
                            <img v-if="item.cover_path" :src="thumbnailUrl(item.cover_path)" :alt="item.title" class="absolute inset-0 h-full w-full object-cover transition-transform duration-200 ease-out group-hover:scale-[1.03]" loading="lazy" decoding="async" />
                            <div v-else class="grid h-full w-full place-items-center text-meta text-subtle">无封面</div>
                            <span class="pointer-events-none absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/8 transition-colors group-hover:ring-white/20" />
                            <span v-if="item.media_type" class="absolute top-2 left-2 inline-flex h-6 items-center rounded-md bg-black/60 px-1.5 text-caption font-medium text-white/90">{{ typeMeta[item.media_type]?.label ?? item.media_type }}</span>
                          </div>
                          <p class="mt-2.5 line-clamp-2 min-h-[2.75em] px-0.5 text-meta font-medium leading-snug text-ink sm:text-body sm:leading-snug" :title="item.title">{{ item.title }}</p>
                        </RouterLink>
                        <div class="mt-1 flex items-center justify-between gap-1 px-0.5">
                          <div class="-ml-1.5 flex items-center" role="group" :aria-label="`为《${item.title}》评分`">
                            <button
                              v-for="s in 5"
                              :key="s"
                              type="button"
                              :aria-label="`${s} 星`"
                              :disabled="ratingLoading === item.id"
                              class="grid size-7 place-items-center rounded-md transition-colors focus-ring pointer-coarse:size-8"
                              :class="(hoverStars[item.id] || item.rating) >= s ? 'text-star' : 'text-faint hover:text-star'"
                              @click="quickRate(item, s, $event)"
                              @mouseenter="hoverStars[item.id] = s"
                              @mouseleave="delete hoverStars[item.id]"
                            >
                              <Star :size="15" :fill="(hoverStars[item.id] || item.rating) >= s ? 'currentColor' : 'none'" aria-hidden="true" />
                            </button>
                          </div>
                        </div>
                        <p class="px-0.5 text-caption text-subtle">{{ lastOpenedText(item) }}</p>
                      </div>
                    </div>
                  </div>

                  <!-- 尘封的高分作品 -->
                  <div v-if="attention.dusty.length && (attentionFilter === 'all' || attentionFilter === 'dusty')">
                    <div class="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                      <h3 class="flex items-center gap-2 text-body font-medium text-ink">尘封的高分作品<span class="text-meta font-normal text-subtle tabular-nums">{{ attention.dusty.length }} 部</span></h3>
                      <p class="text-meta text-subtle">评分 ≥ 4，超过 {{ attention.stale_days }} 天未打开</p>
                    </div>
                    <div class="poster-grid">
                      <RouterLink v-for="item in attention.dusty" :key="item.id" :to="`/?media=${item.id}`" class="group flex min-w-0 flex-col rounded-2xl focus-ring">
                        <div class="relative aspect-[3/4] overflow-hidden rounded-2xl bg-surface-2">
                          <img v-if="item.cover_path" :src="thumbnailUrl(item.cover_path)" :alt="item.title" class="absolute inset-0 h-full w-full object-cover transition-transform duration-200 ease-out group-hover:scale-[1.03]" loading="lazy" decoding="async" />
                          <div v-else class="grid h-full w-full place-items-center text-meta text-subtle">无封面</div>
                          <span class="pointer-events-none absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/8 transition-colors group-hover:ring-white/20" />
                          <span v-if="item.media_type" class="absolute top-2 left-2 inline-flex h-6 items-center rounded-md bg-black/60 px-1.5 text-caption font-medium text-white/90">{{ typeMeta[item.media_type]?.label ?? item.media_type }}</span>
                        </div>
                        <p class="mt-2.5 line-clamp-2 min-h-[2.75em] px-0.5 text-meta font-medium leading-snug text-ink sm:text-body sm:leading-snug" :title="item.title">{{ item.title }}</p>
                        <p class="mt-1 flex items-center justify-between gap-2 px-0.5 text-caption text-subtle">
                          <span class="flex items-center gap-1 text-star tabular-nums"><Star :size="12" fill="currentColor" aria-hidden="true" />{{ item.rating }}</span>
                          <span class="truncate">{{ lastOpenedText(item) }}</span>
                        </p>
                      </RouterLink>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <UiCard v-else-if="attention" padding="none">
              <EmptyState compact :icon="Sparkles" title="暂无待整理作品" description="没有已看未评或尘封的高分作品，媒体库井井有条。" />
            </UiCard>
          </section>
        </div>
      </div>
    </div>

    <!-- 热力图浮窗 -->
    <Teleport to="body">
      <Transition name="tooltip-fade">
        <div
          v-if="heatmapTooltip.visible && heatmapTooltip.day"
          role="tooltip"
          class="stats-tooltip pointer-events-none fixed z-[60] rounded-lg border border-line-strong bg-surface-3 px-3 py-2 text-meta whitespace-nowrap shadow-pop"
          :style="{ left: `${heatmapTooltip.x}px`, top: `${heatmapTooltip.y}px` }"
        >
          <p class="flex items-baseline gap-2">
            <span class="font-medium text-ink tabular-nums">{{ heatmapTooltip.day.formattedDate }}</span>
            <span class="text-caption text-subtle">{{ heatmapTooltip.day.dayName }}</span>
          </p>
          <p class="mt-0.5 flex items-center gap-2 tabular-nums" :class="heatmapTooltip.day.count > 0 ? 'text-muted' : 'text-subtle'">
            {{ heatmapTooltip.day.count > 0 ? `打开 ${heatmapTooltip.day.count} 次` : '无媒体访问记录' }}
            <span v-if="heatmapTooltip.day.level === 4" class="inline-flex h-5 items-center rounded-md bg-accent/15 px-1.5 text-caption font-medium text-accent-glow">活跃峰值</span>
          </p>
        </div>
      </Transition>
    </Teleport>

    <!-- 增长趋势浮窗 -->
    <Teleport to="body">
      <Transition name="tooltip-fade">
        <div
          v-if="growthTooltip.visible && growthTooltip.point"
          role="tooltip"
          class="stats-tooltip pointer-events-none fixed z-[60] min-w-44 rounded-lg border border-line-strong bg-surface-3 px-3 py-2.5 text-meta whitespace-nowrap shadow-pop"
          :style="{ left: `${growthTooltip.x}px`, top: `${growthTooltip.y}px` }"
        >
          <div class="mb-1.5 flex items-center justify-between gap-3 border-b border-line-strong pb-1.5">
            <span class="font-medium text-ink">{{ growthTooltip.point.fullLabel }}</span>
            <span
              v-if="growthTooltip.point.momChange"
              class="inline-flex h-5 items-center rounded-md px-1.5 text-caption font-medium tabular-nums"
              :class="growthTooltip.point.isPositiveMom ? 'bg-success/12 text-success' : 'bg-danger/12 text-danger'"
            >{{ growthTooltip.point.momChange }}</span>
          </div>
          <dl class="space-y-0.5 tabular-nums">
            <div class="flex items-center justify-between gap-4"><dt class="text-subtle">当月新增</dt><dd class="text-ink">+{{ growthTooltip.point.added.toLocaleString() }} 部</dd></div>
            <div class="flex items-center justify-between gap-4"><dt class="text-subtle">全库占比</dt><dd class="text-ink">{{ growthTooltip.point.pctOfTotal }}%</dd></div>
            <div class="flex items-center justify-between gap-4"><dt class="text-subtle">截止累计</dt><dd class="text-ink">{{ growthTooltip.point.cumulative.toLocaleString() }} 部</dd></div>
          </dl>
        </div>
      </Transition>
    </Teleport>

    <!-- 星级打分 Toast -->
    <Teleport to="body">
      <Transition name="toast-fade">
        <div
          v-if="rateToast"
          role="status"
          class="stats-toast fixed right-6 bottom-6 z-[270] flex max-w-sm items-start gap-3 rounded-2xl border border-line-strong bg-surface-3 px-4 py-3 text-body text-ink shadow-pop"
        >
          <Star class="mt-0.5 shrink-0 text-star" :size="18" fill="currentColor" aria-hidden="true" />
          <span class="min-w-0 break-words">{{ rateToast }}</span>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.stats-tooltip {
  transform: translate(-50%, calc(-100% - 8px));
}
.tooltip-fade-enter-active,
.tooltip-fade-leave-active,
.toast-fade-enter-active,
.toast-fade-leave-active {
  transition: opacity var(--duration-fast) var(--ease-out);
}
.tooltip-fade-enter-from,
.tooltip-fade-leave-to,
.toast-fade-enter-from,
.toast-fade-leave-to {
  opacity: 0;
}
@media (max-width: 899px) {
  .stats-toast {
    left: 16px;
    right: 16px;
    max-width: none;
    bottom: calc(var(--he-nav-height, 80px) + env(safe-area-inset-bottom) + 12px);
  }
}
</style>
