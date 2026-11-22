<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { ArrowUpDown, Ban, Check, ChevronDown, ChevronLeft, ChevronRight, Columns3, Eye, Layers, LayoutGrid, List, Play, Rows3, Search, Shuffle, SlidersHorizontal, Star, Tag as TagIcon, TriangleAlert, Trash2, X } from 'lucide-vue-next'
import { API_BASE_URL, thumbnailUrl } from '../config'
import { authHeaders, authIdentity, authState } from '../auth'
import { desktopBridge } from '../desktop'
import mediaPlaceholderUrl from '../assets/media-placeholder.svg?no-inline'
import type { Media, Tag } from '../types'
import DiscardContentDialog from '../components/DiscardContentDialog.vue'
import type { DiscardTarget, DiscardRecord } from '../utils/discardApi'
import MediaCard from '../components/MediaCard.vue'
import MediaViewCard from '../components/MediaViewCard.vue'
import { AsyncMediaDetail as MediaDetail } from '../components/asyncComponents'
import PaginationControl from '../components/PaginationControl.vue'
import { EmptyState, PageHeader, SectionHeader, UiButton, UiIconButton, UiInput, UiSegmented, UiSkeleton, UiToast, buttonClass, controlClass, iconButtonClass, menuItemClass, popoverClass, type SegmentedOption } from '../components/ui'
import { useCompactViewport } from '../composables/useCompactViewport'
import { applyDensity, DENSITY_OPTIONS, densityState, type VisualDensity } from '../density'
const compact = useCompactViewport()
const filterPanelRef = ref<HTMLElement | null>(null)
const filterTriggerRef = ref<HTMLButtonElement | null>(null)
const searchInputRef = ref<{ focus: () => void } | null>(null)

const props = defineProps<{
  mediaType?: string
}>()

const route = useRoute()
const router = useRouter()
const mediaList = ref<Media[]>([])
const continueMedia = ref<Media[]>([])
const tags = ref<Tag[]>([])
const loading = ref(true)
const delayedLoading = ref(false)
let loadingNoticeTimer: number | undefined
const mediaError = ref(''), openingMedia = ref(false), openingError = ref('')
const discardTarget = ref<DiscardTarget | null>(null)
const discardNotice = ref('')
const hiddenDuplicatesCount = ref(0)
const hiddenDupNoticeDismissed = ref(false)
const afterDiscard = async (record: DiscardRecord) => {
  discardNotice.value = record.cleanup_error || ''
  closeMedia(); await fetchMedia(); await fetchContinueMedia()
}
const selectedMedia = ref<Media | null>(null)
const searchQuery = ref(typeof route.query.search === 'string' ? route.query.search : '')
const validSort = (value: unknown): 'date' | 'title' | 'rating' | 'opened' | 'random' =>
  value === 'title' || value === 'rating' || value === 'opened' || value === 'random' ? value : 'date'
const sortBy = ref(validSort(route.query.sort))
const parseSeed = (value: unknown) => {
  const n = Number(Array.isArray(value) ? value[0] : value)
  return Number.isSafeInteger(n) && n > 0 ? n : Math.floor(Math.random() * 900000) + 100000
}
const randomSeed = ref(parseSeed(route.query.seed))
const validViewStatus = (value: unknown): '' | 'unviewed' | 'viewing' | 'viewed' =>
  value === 'unviewed' || value === 'viewing' || value === 'viewed' ? value : ''
const viewStatusFilter = ref(validViewStatus(route.query.view_status))
const validMinRating = (value: unknown): '' | '1' | '3' | '4' | '5' =>
  value === '1' || value === '3' || value === '4' || value === '5' ? value : ''
const minRatingFilter = ref(validMinRating(route.query.min_rating))
const parseCsvTags = (raw: unknown): string[] => {
  const value = Array.isArray(raw) ? raw.join(',') : typeof raw === 'string' ? raw : ''
  const seen = new Set<string>()
  const out: string[] = []
  for (const part of value.split(',')) {
    const cleaned = part.trim()
    if (cleaned && !seen.has(cleaned)) {
      seen.add(cleaned)
      out.push(cleaned)
    }
  }
  return out
}
const readIncludedTagsFromQuery = (query: typeof route.query) => {
  const list = [...parseCsvTags(query.tag), ...parseCsvTags(query.tags)]
  return [...new Set(list)]
}
const validTagMode = (value: unknown): 'all' | 'any' => (value === 'any' ? 'any' : 'all')

const includedTags = ref<string[]>(readIncludedTagsFromQuery(route.query))
const excludedTags = ref<string[]>(parseCsvTags(route.query.exclude_tags))
const tagMode = ref<'all' | 'any'>(validTagMode(route.query.tag_mode))
const selectedNamespace = ref(typeof route.query.tag_namespace === 'string' ? route.query.tag_namespace : '')
const dropdownNamespace = ref(selectedNamespace.value)
const tagDropdownOpen = ref(false)
const tagSearchQuery = ref('')
const tagDropdownRef = ref<HTMLElement | null>(null)
const tagButtonRef = ref<HTMLButtonElement | null>(null)
const tagSearchRef = ref<HTMLInputElement | null>(null)
const favoriteOnly = ref(route.query.favorite === 'true')
const validSource = (value: unknown): '' | 'x' | 'wnacg' | 'local' => value === 'x' || value === 'wnacg' || value === 'local' ? value : ''
const sourceFilter = ref(validSource(route.query.source))
const filtersExpanded = ref(false)
const continueSectionRef = ref<HTMLElement | null>(null)
const continueScrollRef = ref<HTMLElement | null>(null)
const continueCollapsed = ref(localStorage.getItem('he_continue_collapsed') === 'true')
const hiddenContinueIds = ref<Set<number>>(new Set())

type MediaViewMode = 'poster' | 'list' | 'masonry' | 'wide'
const viewMode = ref<MediaViewMode>('poster')
// Keep the visible cards paired with the layout of the committed result.
const displayedLayout = ref<{ type?: string; mode: MediaViewMode } | null>(null)
const displayedType = computed(() => displayedLayout.value ? displayedLayout.value.type : props.mediaType)
const displayedView = computed(() => displayedLayout.value?.mode ?? viewMode.value)
const viewOptions = computed(() => {
  const options: { mode: MediaViewMode; label: string; icon: typeof LayoutGrid }[] = [
    { mode: 'poster', label: '海报网格', icon: LayoutGrid },
    { mode: 'list', label: '紧凑列表', icon: List },
  ]
  if (props.mediaType === 'image' || props.mediaType === 'manga') {
    options.push({ mode: 'masonry', label: '瀑布流', icon: Columns3 })
  }
  if (props.mediaType === 'video') {
    options.push({ mode: 'wide', label: '宽幅卡片', icon: Rows3 })
  }
  return options
})

const viewStorageKey = () => `he_media_view_${props.mediaType || 'all'}`
const isAvailableView = (value: unknown): value is MediaViewMode =>
  typeof value === 'string' && viewOptions.value.some(option => option.mode === value)

watch([() => props.mediaType, () => route.query.view], () => {
  const queryView = Array.isArray(route.query.view) ? route.query.view[0] : route.query.view
  let savedView: string | null = null
  try {
    savedView = localStorage.getItem(viewStorageKey())
    if (isAvailableView(queryView)) localStorage.setItem(viewStorageKey(), queryView)
  } catch {
    // The current route still works when browser storage is unavailable.
  }
  viewMode.value = isAvailableView(queryView) ? queryView : isAvailableView(savedView) ? savedView : props.mediaType === 'video' && compact.value ? 'wide' : props.mediaType === 'audio' && compact.value ? 'list' : 'poster'
}, { immediate: true })

const selectViewMode = (mode: MediaViewMode) => {
  if (!isAvailableView(mode) || mode === viewMode.value) return
  viewMode.value = mode
  try {
    localStorage.setItem(viewStorageKey(), mode)
  } catch {
    // View switching does not depend on browser storage.
  }
  void router.replace({ path: route.path, query: { ...route.query, view: mode } })
}

watch(continueCollapsed, (val) => {
  localStorage.setItem('he_continue_collapsed', String(val))
})

const TAG_NAMESPACE_LABELS: Record<string, string> = {
  general: '通用',
  artist: '作者',
  circle: '社团',
  parody: '原作',
  character: '角色',
  category: '分类',
  language: '语言',
  source: '来源',
}
const formatNamespaceLabel = (ns: string) => TAG_NAMESPACE_LABELS[ns] ?? ns

const availableNamespaces = computed(() => {
  const counts = new Map<string, number>()
  for (const tag of tags.value) {
    const ns = tag.namespace || 'general'
    counts.set(ns, (counts.get(ns) ?? 0) + 1)
  }
  if (counts.size <= 1 && !selectedNamespace.value) return []
  return [...counts.entries()].map(([value, count]) => ({
    value,
    label: formatNamespaceLabel(value),
    count,
  }))
})

const filteredTags = computed(() => {
  const query = tagSearchQuery.value.trim().toLowerCase()
  const nsFilter = dropdownNamespace.value || selectedNamespace.value
  return tags.value.filter(tag => {
    if (nsFilter && (tag.namespace || 'general') !== nsFilter) return false
    if (query && !tag.name.toLowerCase().includes(query)) return false
    return true
  })
})

const hasTagFilter = computed(() =>
  includedTags.value.length > 0 || excludedTags.value.length > 0 || Boolean(selectedNamespace.value)
)

const advancedFilterCount = computed(() => {
  return includedTags.value.length +
    excludedTags.value.length +
    Number(Boolean(selectedNamespace.value)) +
    Number(Boolean(sourceFilter.value)) +
    Number(Boolean(viewStatusFilter.value)) +
    Number(Boolean(minRatingFilter.value))
})

const activeFilterCount = computed(() => {
  return advancedFilterCount.value +
    Number(sortBy.value !== 'date') +
    Number(Boolean(searchQuery.value)) +
    Number(Boolean(favoriteOnly.value))
})

const clearFilters = () => {
  window.clearTimeout(searchTimer)
  tagSearchQuery.value = ''
  // Update the route once; its watcher restores every filter together.
  // Mutating the refs first lets their watchers reinsert the old query.
  const query = { ...route.query }
  delete query.page
  delete query.search
  delete query.tag
  delete query.tags
  delete query.tag_mode
  delete query.exclude_tags
  delete query.tag_namespace
  delete query.sort
  delete query.seed
  delete query.source
  delete query.view_status
  delete query.min_rating
  delete query.favorite
  void router.replace({ path: route.path, query })
}

const dismissContinueItem = (id: number, event: MouseEvent) => {
  event.stopPropagation()
  hiddenContinueIds.value = new Set([...hiddenContinueIds.value, id])
}

const scrollContinue = (direction: -1 | 1) => {
  const el = continueScrollRef.value
  if (!el) return
  el.scrollBy({ left: direction * Math.max(220, el.clientWidth * 0.72), behavior: 'smooth' })
}

const continueDragging = ref(false)
let continuePointer: { id: number; x: number; scrollLeft: number; moved: boolean } | null = null
let suppressContinueClick = false
let continueClickTimer: number | undefined
const startContinueDrag = (event: PointerEvent) => {
  if (event.pointerType !== 'mouse' || event.button !== 0 || !continueScrollRef.value) return
  suppressContinueClick = false
  window.clearTimeout(continueClickTimer)
  continuePointer = { id: event.pointerId, x: event.clientX, scrollLeft: continueScrollRef.value.scrollLeft, moved: false }
}
const moveContinueDrag = (event: PointerEvent) => {
  const el = continueScrollRef.value, drag = continuePointer
  if (!el || !drag || event.pointerId !== drag.id) return
  const distance = event.clientX - drag.x
  if (!drag.moved && Math.abs(distance) < 6) return
  if (!drag.moved) {
    drag.moved = true
    continueDragging.value = true
    el.setPointerCapture(event.pointerId)
  }
  event.preventDefault()
  el.scrollLeft = drag.scrollLeft - distance
}
const endContinueDrag = (event: PointerEvent) => {
  if (!continuePointer || event.pointerId !== continuePointer.id) return
  if (continuePointer.moved) {
    suppressContinueClick = true
    continueClickTimer = window.setTimeout(() => { suppressContinueClick = false }, 0)
  }
  continuePointer = null
  continueDragging.value = false
}
const preventDraggedClick = (event: MouseEvent) => {
  if (!suppressContinueClick || event.detail === 0) return
  suppressContinueClick = false
  event.preventDefault()
  event.stopPropagation()
}

const showOtherContinueItems = async () => {
  continueCollapsed.value = false
  await nextTick()
  const section = continueSectionRef.value
  if (!section) return
  section.style.scrollMarginTop = '16px'
  section.scrollIntoView({
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    block: 'start',
  })
}

const progressPercent = (media: Media) => {
  if (media.media_type === 'video' && media.duration && media.duration > 0 && media.progress > 0) {
    return Math.min(100, Math.max(0, Math.round((media.progress / media.duration) * 100)))
  }
  // Manga progress is a 0-based page index, so page 0 only counts once reading started.
  if (media.media_type === 'manga' && media.page_count && media.page_count > 0 && media.progress >= 0 && media.view_status !== 'unviewed') {
    return Math.min(100, Math.max(0, Math.round(((media.progress + 1) / media.page_count) * 100)))
  }
  return 0
}

const typeLabel = (type: Media['media_type']) =>
  type === 'video' ? '视频' : type === 'manga' ? '漫画' : type === 'audio' ? '音频' : '杂图'

const formatClock = (seconds: number) => {
  const total = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = String(total % 60).padStart(2, '0')
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${rest}` : `${minutes}:${rest}`
}

const continueMeta = (media: Media) => {
  const percent = progressPercent(media)
  if (media.media_type === 'manga' && media.page_count) {
    return percent > 0 ? `${Math.min(media.page_count, media.progress + 1)}/${media.page_count} 页` : `${media.page_count} 页`
  }
  if (percent > 0) return `已看 ${percent}%`
  if (media.duration) return formatClock(media.duration)
  return ''
}

const continueThumbClass = (media: Media) =>
  media.media_type === 'video' ? 'w-24' : media.media_type === 'audio' ? 'w-16' : 'w-11'

const continueTitle = computed(() =>
  displayedType.value === 'manga' ? '继续阅读' : displayedType.value === 'audio' ? '继续收听' : displayedType.value === 'image' ? '最近浏览' : '继续观看')

const recentlyOpened = computed(() => {
  return [...continueMedia.value]
    .filter(item => (!desktopBridge || item.view_status === 'viewing') && !hiddenContinueIds.value.has(item.id) && (item.last_opened_at || progressPercent(item) > 0))
    .sort((a, b) => {
      const timeA = a.last_opened_at ? new Date(a.last_opened_at).getTime() : 0
      const timeB = b.last_opened_at ? new Date(b.last_opened_at).getTime() : 0
      return timeB - timeA
    })
    .slice(0, 8)
})

const featuredContinue = computed(() => recentlyOpened.value[0] ?? null)
const otherContinueItems = computed(() => recentlyOpened.value.slice(1))

const drawerDragY = ref(0)
let drawerTouchStartY = 0
let drawerDragging = false
const onDrawerTouchStart = (event: TouchEvent) => {
  if (!compact.value || event.touches.length !== 1) return
  drawerTouchStartY = event.touches[0]!.clientY
  drawerDragging = true
}
const onDrawerTouchMove = (event: TouchEvent) => {
  if (!drawerDragging || event.touches.length !== 1) return
  const dy = event.touches[0]!.clientY - drawerTouchStartY
  if (dy > 0) drawerDragY.value = Math.min(dy, 220)
}
const onDrawerTouchEnd = () => {
  if (!drawerDragging) return
  drawerDragging = false
  if (drawerDragY.value > 72) filtersExpanded.value = false
  drawerDragY.value = 0
}

const basePageSize = desktopBridge ? 60 : 36
const pageSize = ref(basePageSize)
const totalItems = ref(0)
const containerRef = ref<HTMLElement | null>(null)
let gridObserver: ResizeObserver | undefined
let gridResizeTimer: number | undefined
let pendingGridMeasurement = false

const routePage = (value: unknown) => {
  const raw = Array.isArray(value) ? value[0] : value
  const parsed = Number(raw)
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1
}

const currentPage = ref(routePage(route.query.page))
const pageCount = computed(() => Math.max(1, Math.ceil(totalItems.value / pageSize.value)))
const viewerMediaList = ref<Media[]>([])
const viewerFirstPage = ref(currentPage.value)
const viewerLastPage = ref(currentPage.value)
const viewerPageLoading = ref(false)
let hasCompletedInitialFetch = false
let mediaRequestId = 0
let disposed = false, detailRequestId = 0
const controllers = new Map<string, AbortController>()
const requestScope = (name: string) => {
  controllers.get(name)?.abort()
  const controller = new AbortController(); controllers.set(name, controller)
  return { signal: controller.signal, headers: authHeaders() }
}
let viewerPageRequestId = 0

const syncPageQuery = (page: number, replace = false) => {
  const query = { ...route.query }
  if (page <= 1) delete query.page
  else query.page = String(page)
  const location = { path: route.path, query }
  void (replace ? router.replace(location) : router.push(location))
}

const mediaParamsForPage = (page: number): Record<string, string | number | boolean | undefined> => ({
  media_type: props.mediaType,
  search: searchQuery.value.trim() || undefined,
  tag: includedTags.value.length === 1 ? includedTags.value[0] : undefined,
  tags: includedTags.value.length > 1 ? includedTags.value.join(',') : undefined,
  tag_mode: includedTags.value.length > 1 ? tagMode.value : undefined,
  exclude_tags: excludedTags.value.length ? excludedTags.value.join(',') : undefined,
  tag_namespace: selectedNamespace.value || undefined,
  favorite: favoriteOnly.value ? true : undefined,
  view_status: viewStatusFilter.value || undefined,
  min_rating: minRatingFilter.value ? Number(minRatingFilter.value) : undefined,
  source_site: sourceFilter.value || undefined,
  sort: sortBy.value,
  seed: sortBy.value === 'random' ? randomSeed.value : undefined,
  limit: pageSize.value,
  offset: (page - 1) * pageSize.value,
})

const resetViewerMediaList = (media?: Media) => {
  viewerPageRequestId += 1
  viewerPageLoading.value = false
  const pageItems = [...mediaList.value]
  viewerMediaList.value = media && !pageItems.some(item => item.id === media.id) ? [media] : pageItems
  viewerFirstPage.value = currentPage.value
  viewerLastPage.value = currentPage.value
}

const scrollToTop = (behavior: ScrollBehavior = 'auto') => {
  const scrollRoot = containerRef.value?.closest<HTMLElement>('.main-scroll-container')
    || document.querySelector<HTMLElement>('.main-scroll-container')
  if (!scrollRoot) return
  if (behavior === 'auto') {
    scrollRoot.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior })
    scrollRoot.scrollTop = 0
  } else {
    scrollRoot.scrollTo({ top: 0, behavior })
  }
}

const pageTitle = computed(() => {
  if (props.mediaType === 'video') return '所有视频'
  if (props.mediaType === 'manga') return '所有漫画'
  if (props.mediaType === 'image') return '所有杂图'
  if (props.mediaType === 'audio') return '所有音频'
  if (favoriteOnly.value) return '我的收藏'
  return '全部媒体'
})

const selectedTagLabel = computed(() => {
  if (includedTags.value.length === 1 && excludedTags.value.length === 0 && !selectedNamespace.value) {
    return includedTags.value[0]!
  }
  const parts: string[] = []
  if (selectedNamespace.value) parts.push(formatNamespaceLabel(selectedNamespace.value))
  if (includedTags.value.length > 0) parts.push(`已选 ${includedTags.value.length}`)
  if (excludedTags.value.length > 0) parts.push(`排除 ${excludedTags.value.length}`)
  return parts.length ? parts.join(' · ') : '全部标签'
})

type SortKey = 'date' | 'title' | 'rating' | 'opened' | 'random'
const sortOptions: SegmentedOption<SortKey>[] = [
  { value: 'date', label: '最近添加' },
  { value: 'opened', label: '最近打开' },
  { value: 'rating', label: '评分' },
  { value: 'title', label: '名称' },
  { value: 'random', label: '随机漫游' },
]
const sortLabel = computed(() => sortOptions.find(option => option.value === sortBy.value)?.label ?? '最近添加')
const sourceOptions: SegmentedOption<'' | 'x' | 'wnacg' | 'local'>[] = [
  { value: '', label: '全部来源' },
  { value: 'local', label: '本地' },
  { value: 'x', label: 'X' },
  { value: 'wnacg', label: 'WNACG' },
]
const sourceLabel = computed(() => sourceOptions.find(option => option.value === sourceFilter.value)?.label ?? '全部来源')
const viewStatusOptions: SegmentedOption<'' | 'unviewed' | 'viewing' | 'viewed'>[] = [
  { value: '', label: '全部状态' },
  { value: 'unviewed', label: '未看' },
  { value: 'viewing', label: '在看' },
  { value: 'viewed', label: '已看' },
]
const viewStatusLabel = computed(() => viewStatusOptions.find(option => option.value === viewStatusFilter.value)?.label ?? '全部状态')
const ratingOptions: SegmentedOption<'' | '1' | '3' | '4' | '5'>[] = [
  { value: '', label: '全部评分' },
  { value: '1', label: '1★+' },
  { value: '3', label: '3★+' },
  { value: '4', label: '4★+' },
  { value: '5', label: '5★' },
]
const minRatingLabel = computed(() => ratingOptions.find(option => option.value === minRatingFilter.value)?.label ?? '全部评分')
const densityOptions: SegmentedOption<VisualDensity>[] = DENSITY_OPTIONS.map(option => ({
  value: option.id,
  label: option.shortLabel,
}))
const densityModel = computed<VisualDensity>({
  get: () => densityState.density,
  set: mode => applyDensity(mode),
})
const viewSegments = computed<SegmentedOption<MediaViewMode>[]>(() => viewOptions.value.map(option => ({
  value: option.mode, label: option.label, icon: option.icon, iconOnly: !compact.value,
})))
const viewModeModel = computed<MediaViewMode>({
  get: () => viewMode.value,
  set: mode => selectViewMode(mode),
})

// Single-type pages keep their natural covers, including wide video stills.
const cardShape = computed(() => displayedType.value && displayedType.value !== 'image' ? 'natural' : 'poster')
const posterGridClass = computed(() => displayedType.value === 'video' && cardShape.value === 'natural'
  ? 'grid grid-cols-1 gap-x-5 gap-y-7 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4'
  : 'poster-grid he-subgrid-wall')
const skeletonAspect = computed(() => viewMode.value === 'wide' || (viewMode.value === 'poster' && props.mediaType === 'video')
  ? 'aspect-video'
  : viewMode.value === 'poster' && props.mediaType === 'audio' ? 'aspect-square' : 'aspect-[2/3]')

const measurePageSize = (refresh = true) => {
  if (route.query.media || openingMedia.value || selectedMedia.value) { pendingGridMeasurement = true; return }
  pendingGridMeasurement = false
  const grid = containerRef.value?.querySelector<HTMLElement>('[data-media-grid]')
  let columns = 1
  if ((displayedView.value === 'poster' || displayedView.value === 'wide') && grid) {
    const tracks = getComputedStyle(grid).gridTemplateColumns
    if (tracks && tracks !== 'none') columns = Math.max(1, tracks.trim().split(/\s+/).length)
  }
  const nextSize = Math.max(columns, Math.floor(basePageSize / columns) * columns)
  if (nextSize === pageSize.value) return
  const anchor = (currentPage.value - 1) * pageSize.value
  pageSize.value = nextSize
  const nextPage = Math.floor(anchor / nextSize) + 1
  if (nextPage !== currentPage.value) {
    currentPage.value = nextPage
    syncPageQuery(nextPage, true)
  } else if (refresh) void fetchMedia()
}

const scheduleGridMeasurement = () => {
  window.clearTimeout(gridResizeTimer)
  window.clearTimeout(continueClickTimer)
  gridResizeTimer = window.setTimeout(() => measurePageSize(), 150)
}

const sortDropdownOpen = ref(false)
const sortDropdownRef = ref<HTMLElement | null>(null)
const sortButtonRef = ref<HTMLButtonElement | null>(null)
const selectSort = (value: SortKey) => {
  if (value === 'random') {
    randomSeed.value = Math.floor(Math.random() * 900000) + 100000
  }
  sortBy.value = value
  sortDropdownOpen.value = false
  sortButtonRef.value?.focus()
}
const reshuffleRandom = () => {
  randomSeed.value = Math.floor(Math.random() * 900000) + 100000
  if (sortBy.value !== 'random') sortBy.value = 'random'
  else syncFilters()
}

const toggleIncludeTag = (tagName: string) => {
  excludedTags.value = excludedTags.value.filter(t => t !== tagName)
  if (includedTags.value.includes(tagName)) {
    includedTags.value = includedTags.value.filter(t => t !== tagName)
  } else {
    includedTags.value = [...includedTags.value, tagName]
  }
}

const toggleExcludeTag = (tagName: string) => {
  includedTags.value = includedTags.value.filter(t => t !== tagName)
  if (excludedTags.value.includes(tagName)) {
    excludedTags.value = excludedTags.value.filter(t => t !== tagName)
  } else {
    excludedTags.value = [...excludedTags.value, tagName]
  }
}

const clearTagFilters = () => {
  includedTags.value = []
  excludedTags.value = []
  selectedNamespace.value = ''
  dropdownNamespace.value = ''
  tagSearchQuery.value = ''
  tagDropdownOpen.value = false
}

const toggleNamespaceFilter = (ns: string) => {
  if (!ns) {
    dropdownNamespace.value = ''
    selectedNamespace.value = ''
    return
  }
  dropdownNamespace.value = ns
  selectedNamespace.value = selectedNamespace.value === ns ? '' : ns
}

const closeTagDropdown = async () => {
  tagDropdownOpen.value = false
  await nextTick()
  tagButtonRef.value?.focus()
}

const handleTagOutsidePointer = (event: PointerEvent) => {
  if (tagDropdownOpen.value && !tagDropdownRef.value?.contains(event.target as Node)) {
    tagDropdownOpen.value = false
  }
  if (sortDropdownOpen.value && !sortDropdownRef.value?.contains(event.target as Node)) {
    sortDropdownOpen.value = false
  }
}

watch(tagDropdownOpen, async (open) => {
  if (!open) return
  await nextTick()
  tagSearchRef.value?.focus()
})

const fetchTags = async () => {
  if (disposed) return
  const scope = requestScope('tags'), identity = authIdentity()
  try {
    const res = await axios.get(`${API_BASE_URL}/tags`, scope)
    if (!disposed && !scope.signal.aborted && identity === authIdentity()) tags.value = res.data
  } catch (err) {
    if (!axios.isCancel(err)) console.error('Failed to fetch tags:', err)
  }
}

const fetchContinueMedia = async (commit = true) => {
  if (disposed) return
  const scope = requestScope('continue'), identity = authIdentity()
  try {
    const res = await axios.get<Media[]>(`${API_BASE_URL}/media`, {
      ...scope, params: { media_type: props.mediaType, sort: 'opened', ...(desktopBridge ? { view_status: 'viewing' } : {}), limit: 12, offset: 0 },
    })
    if (!disposed && !scope.signal.aborted && identity === authIdentity()) {
      if (commit) continueMedia.value = res.data
      return res.data
    }
  } catch (err) {
    if (!axios.isCancel(err)) console.error('Failed to fetch continue-watching media:', err)
    if (!disposed && !scope.signal.aborted && identity === authIdentity()) {
      if (commit) continueMedia.value = []
      return [] as Media[]
    }
  }
}

const fetchMedia = async (scrollBehavior: ScrollBehavior = 'auto') => {
  if (disposed) return
  const scope = requestScope('list'), identity = authIdentity()
  const requestId = ++mediaRequestId
  const requestedType = props.mediaType
  const refreshContinue = !displayedLayout.value || displayedLayout.value.type !== requestedType
  if (hasCompletedInitialFetch && scrollBehavior !== 'auto') scrollToTop(scrollBehavior)
  loading.value = true
  window.clearTimeout(loadingNoticeTimer)
  delayedLoading.value = false
  loadingNoticeTimer = window.setTimeout(() => {
    if (!disposed && requestId === mediaRequestId && mediaList.value.length) delayedLoading.value = true
  }, 300)
  mediaError.value = ''
  try {
    const [res, nextContinue] = await Promise.all([
      axios.get<Media[]>(`${API_BASE_URL}/media`, { ...scope, params: mediaParamsForPage(currentPage.value) }),
      refreshContinue ? fetchContinueMedia(false) : Promise.resolve(undefined),
    ])
    if (disposed || scope.signal.aborted || identity !== authIdentity() || requestId !== mediaRequestId) return

    const headerTotal = Number(res.headers['x-total-count'])
    totalItems.value = Number.isSafeInteger(headerTotal) && headerTotal >= 0
      ? headerTotal
      : (currentPage.value - 1) * pageSize.value + res.data.length
    const headerHiddenDup = Number(res.headers['x-hidden-duplicates-count'])
    hiddenDuplicatesCount.value = Number.isSafeInteger(headerHiddenDup) && headerHiddenDup >= 0 ? headerHiddenDup : 0

    const lastPage = Math.max(1, Math.ceil(totalItems.value / pageSize.value))
    if (currentPage.value > lastPage) {
      currentPage.value = lastPage
      syncPageQuery(lastPage, true)
      await fetchMedia()
      return
    }
    displayedLayout.value = { type: requestedType, mode: viewMode.value }
    if (nextContinue !== undefined) continueMedia.value = nextContinue
    mediaList.value = res.data
  } catch (err: any) {
    if (disposed || scope.signal.aborted || identity !== authIdentity() || requestId !== mediaRequestId) return
    console.error('Failed to fetch media:', err)
    mediaList.value = []
    totalItems.value = 0
    const status = err?.response?.status
    mediaError.value = status === 401
      ? '登录状态已失效，请重新登录。'
      : status === 403
        ? '当前账号没有权限读取媒体列表。'
        : '无法加载媒体列表，请检查后端连接。'
  } finally {
    if (!disposed && requestId === mediaRequestId) {
      window.clearTimeout(loadingNoticeTimer)
      delayedLoading.value = false
      loading.value = false
      hasCompletedInitialFetch = true
      await nextTick()
      window.dispatchEvent(new Event('he:content-ready'))
    }
  }
}

const hasAdjacentViewerPage = (direction: -1 | 1) => {
  const targetPage = direction < 0 ? viewerFirstPage.value - 1 : viewerLastPage.value + 1
  return targetPage >= 1 && targetPage <= pageCount.value
}

const loadAdjacentViewerPage = async (direction: -1 | 1) => {
  if (disposed) return false
  const scope = requestScope('adjacent'), identity = authIdentity()
  if (viewerPageLoading.value || !hasAdjacentViewerPage(direction)) return false
  const targetPage = direction < 0 ? viewerFirstPage.value - 1 : viewerLastPage.value + 1
  const requestId = ++viewerPageRequestId
  viewerPageLoading.value = true
  try {
    const res = await axios.get<Media[]>(`${API_BASE_URL}/media`, { ...scope, params: mediaParamsForPage(targetPage) })
    if (disposed || scope.signal.aborted || identity !== authIdentity() || requestId !== viewerPageRequestId) return false
    const headerTotal = Number(res.headers['x-total-count'])
    if (Number.isSafeInteger(headerTotal) && headerTotal >= 0) totalItems.value = headerTotal
    if (res.data.length === 0) {
      if (direction < 0) viewerFirstPage.value = targetPage
      else viewerLastPage.value = targetPage
      return false
    }
    viewerMediaList.value = direction < 0
      ? [...res.data, ...viewerMediaList.value]
      : [...viewerMediaList.value, ...res.data]
    if (direction < 0) viewerFirstPage.value = targetPage
    else viewerLastPage.value = targetPage
    return true
  } catch (err) {
    if (requestId === viewerPageRequestId) console.error('Failed to load adjacent media page:', err)
    return false
  } finally {
    if (requestId === viewerPageRequestId) viewerPageLoading.value = false
  }
}

const goToPage = (page: number) => {
  const target = Math.max(1, Math.min(page, pageCount.value))
  if (target === currentPage.value || loading.value) return
  const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
  scrollToTop(behavior)
  syncPageQuery(target)
}

const MISSING_RECHECK_COOLDOWN_MS = 15 * 60 * 1000
const MISSING_RECHECK_STORAGE_KEY = 'he_missing_recheck_last_at'
let fallbackMissingRecheckAt = 0

const getLastMissingRecheckAt = () => {
  try {
    const parsed = Number(sessionStorage.getItem(MISSING_RECHECK_STORAGE_KEY) || 0)
    return Number.isFinite(parsed) ? parsed : 0
  } catch {
    return fallbackMissingRecheckAt
  }
}

const setLastMissingRecheckAt = (timestamp: number) => {
  fallbackMissingRecheckAt = timestamp
  try {
    sessionStorage.setItem(MISSING_RECHECK_STORAGE_KEY, String(timestamp))
  } catch {
    // Session storage is optional; fall back to in-memory timestamp.
  }
}

const tagsSignature = (media?: Media | null) =>
  (media?.tags ?? [])
    .map(tag => `${tag.id}:${tag.name}:${tag.namespace ?? ''}`)
    .sort()
    .join('|')

const updateMediaInList = (media: Media) => {
  const index = mediaList.value.findIndex(item => item.id === media.id)
  const viewerIndex = viewerMediaList.value.findIndex(item => item.id === media.id)
  const continueIndex = continueMedia.value.findIndex(item => item.id === media.id)
  const previousMedia =
    (selectedMedia.value?.id === media.id ? selectedMedia.value : undefined) ??
    (index >= 0 ? mediaList.value[index] : undefined) ??
    (viewerIndex >= 0 ? viewerMediaList.value[viewerIndex] : undefined) ??
    (continueIndex >= 0 ? continueMedia.value[continueIndex] : undefined)
  const tagsChanged = Boolean(previousMedia) && tagsSignature(previousMedia) !== tagsSignature(media)

  if (index >= 0) {
    mediaList.value[index] = media
  }
  if (viewerIndex >= 0) viewerMediaList.value[viewerIndex] = media
  if (continueIndex >= 0) {
    continueMedia.value[continueIndex] = media
  } else if (media.last_opened_at || progressPercent(media) > 0) {
    continueMedia.value = [media, ...continueMedia.value].slice(0, 12)
  }
  if (selectedMedia.value?.id === media.id) {
    selectedMedia.value = media
  }
  if (tagsChanged) {
    void fetchTags()
  }
}

const canKeepImageReader = (mediaId: number) => selectedMedia.value?.media_type === 'image'
  && viewerMediaList.value.some(item => item.id === mediaId && item.media_type === 'image' && !item.is_missing)

const openMedia = (media: Media, replace = false) => {
  if (!replace || viewerMediaList.value.length === 0) resetViewerMediaList(media)
  if (!replace || !canKeepImageReader(media.id)) selectedMedia.value = null
  const location = {
    path: route.path,
    query: {
      ...route.query,
      media: String(media.id),
    },
  }

  if (replace) {
    router.replace(location)
  } else {
    router.push(location)
  }
}

const closeMedia = () => {
  ++detailRequestId; controllers.get('detail')?.abort(); openingMedia.value = false
  selectedMedia.value = null
  resetViewerMediaList()
  const query = { ...route.query }
  delete query.media
  void router.replace({ path: route.path, query })
}

const syncSelectedMediaFromRoute = async () => {
  const mediaId = Number(route.query.media), requestId = ++detailRequestId
  controllers.get('detail')?.abort()
  if (!Number.isSafeInteger(mediaId) || mediaId < 1) {
    selectedMedia.value = null; openingMedia.value = false
    return
  }
  if (selectedMedia.value?.id === mediaId) { openingMedia.value = false; return }
  const scope = requestScope('detail'), identity = authIdentity()
  // Image scroll reports update the route too. Keep the reader, decoded pages,
  // scroll position and hidden controls alive while refreshing the selected DTO.
  if (!canKeepImageReader(mediaId)) selectedMedia.value = null
  openingMedia.value = true; openingError.value = ''
  try {
    // The detail route marks last_opened_at. Only an explicit viewer navigation reaches it.
    const res = await axios.get<Media>(`${API_BASE_URL}/media/${mediaId}`, scope)
    if (disposed || scope.signal.aborted || identity !== authIdentity() || requestId !== detailRequestId || Number(route.query.media) !== mediaId) return
    if (!viewerMediaList.value.some(item => item.id === mediaId)) resetViewerMediaList(res.data)
    selectedMedia.value = res.data
    updateMediaInList(res.data)
  } catch (err: any) {
    if (disposed || scope.signal.aborted || identity !== authIdentity() || requestId !== detailRequestId || axios.isCancel(err)) return
    openingError.value = err.response?.status === 404 ? '作品已不存在，请刷新媒体库。' : err.response?.status === 401 ? '登录状态已失效，请重新登录。' : '无法打开作品，请检查连接后重试。'
    closeMedia()
  } finally {
    if (!disposed && requestId === detailRequestId) openingMedia.value = false
  }
}

const toggleFavoriteFilter = () => {
  const nextFavorite = !favoriteOnly.value
  router.push({
    path: route.path,
    query: {
      ...route.query,
      favorite: nextFavorite ? 'true' : undefined,
    },
  })
}

let searchTimer: number | undefined
const syncFilters = () => {
  const desiredSeed = sortBy.value === 'random' ? String(randomSeed.value) : ''
  const desiredSingleTag = includedTags.value.length === 1 ? includedTags.value[0]! : ''
  const desiredMultiTags = includedTags.value.length > 1 ? includedTags.value.join(',') : ''
  const desiredTagMode = includedTags.value.length > 1 && tagMode.value === 'any' ? 'any' : ''
  const desiredExcludeTags = excludedTags.value.length ? excludedTags.value.join(',') : ''
  const current = [
    route.query.search || '',
    route.query.tag || '',
    route.query.tags || '',
    route.query.tag_mode || '',
    route.query.exclude_tags || '',
    route.query.tag_namespace || '',
    validSort(route.query.sort),
    validSource(route.query.source),
    validViewStatus(route.query.view_status),
    validMinRating(route.query.min_rating),
    route.query.sort === 'random' && route.query.seed ? String(route.query.seed) : '',
  ]
  const desired = [
    searchQuery.value,
    desiredSingleTag,
    desiredMultiTags,
    desiredTagMode,
    desiredExcludeTags,
    selectedNamespace.value,
    sortBy.value,
    sourceFilter.value,
    viewStatusFilter.value,
    minRatingFilter.value,
    desiredSeed,
  ]
  if (current.every((value, index) => value === desired[index])) return
  const query = { ...route.query }
  delete query.page
  for (const [key, value] of Object.entries({
    search: searchQuery.value,
    tag: desiredSingleTag,
    tags: desiredMultiTags,
    tag_mode: desiredTagMode,
    exclude_tags: desiredExcludeTags,
    tag_namespace: selectedNamespace.value,
    sort: sortBy.value === 'date' ? '' : sortBy.value,
    seed: desiredSeed,
    source: sourceFilter.value,
    view_status: viewStatusFilter.value,
    min_rating: minRatingFilter.value,
  })) {
    if (value) query[key] = value
    else delete query[key]
  }
  void router.replace({ path: route.path, query })
}
watch(searchQuery, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(syncFilters, 250)
})
watch([includedTags, excludedTags, tagMode, selectedNamespace, sortBy, sourceFilter, viewStatusFilter, minRatingFilter], syncFilters, { deep: true })
watch(() => JSON.stringify([props.mediaType, route.query.search, route.query.tag, route.query.tags, route.query.tag_mode, route.query.exclude_tags, route.query.tag_namespace, route.query.sort, route.query.seed, route.query.source, route.query.view_status, route.query.min_rating, route.query.favorite, route.query.page]), () => {
  window.clearTimeout(searchTimer)
  searchQuery.value = typeof route.query.search === 'string' ? route.query.search : ''
  includedTags.value = readIncludedTagsFromQuery(route.query)
  excludedTags.value = parseCsvTags(route.query.exclude_tags)
  tagMode.value = validTagMode(route.query.tag_mode)
  selectedNamespace.value = typeof route.query.tag_namespace === 'string' ? route.query.tag_namespace : ''
  dropdownNamespace.value = selectedNamespace.value
  sortBy.value = validSort(route.query.sort)
  if (route.query.seed) randomSeed.value = parseSeed(route.query.seed)
  sourceFilter.value = validSource(route.query.source)
  viewStatusFilter.value = validViewStatus(route.query.view_status)
  minRatingFilter.value = validMinRating(route.query.min_rating)
  favoriteOnly.value = route.query.favorite === 'true'
  currentPage.value = routePage(route.query.page)
  void fetchMedia()
})
watch(filtersExpanded, async open => {
  await nextTick()
  if (open) filterPanelRef.value?.querySelector<HTMLElement>('button:not([disabled]), input:not([disabled])')?.focus()
  else filterTriggerRef.value?.focus()
})
const filterKeydown = (event: KeyboardEvent) => {
  if (!filtersExpanded.value) return
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); filtersExpanded.value = false }
  if (event.key !== 'Tab') return
  const buttons = filterPanelRef.value?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), [tabindex="0"]')
  if (!buttons?.length) return
  const first = buttons[0]!, last = buttons[buttons.length - 1]!
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
const mobileCategories = [ { label: '全部', path: '/' }, { label: '漫画', path: '/type/manga' }, { label: '视频', path: '/type/video' }, { label: '音频', path: '/type/audio' }, { label: '图片', path: '/type/image' } ]
watch(() => route.query.media, () => {
  syncSelectedMediaFromRoute()
})
watch(viewMode, mode => {
  if (!loading.value && displayedLayout.value?.type === props.mediaType) {
    displayedLayout.value = { type: props.mediaType, mode }
  }
})
watch([displayedView, displayedType, () => densityState.density], async () => {
  await nextTick()
  scheduleGridMeasurement()
})
watch([selectedMedia, openingMedia, () => route.query.media], () => {
  if (pendingGridMeasurement && !selectedMedia.value && !openingMedia.value && !route.query.media) scheduleGridMeasurement()
})

const onGlobalMediaUpdated = (event: Event) => updateMediaInList((event as CustomEvent<Media>).detail)
const onGlobalHomeKeydown = (event: KeyboardEvent) => {
  if (openingMedia.value && event.key === 'Escape') {
    closeMedia()
    return
  }
  if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey && !selectedMedia.value && !route.query.media) {
    const target = event.target as HTMLElement | null
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable)) return
    event.preventDefault()
    searchInputRef.value?.focus()
  }
}
onUnmounted(() => {
  window.clearTimeout(loadingNoticeTimer)
  disposed = true; ++mediaRequestId; ++detailRequestId; ++viewerPageRequestId
  for (const controller of controllers.values()) controller.abort()
  window.removeEventListener('he:media-updated', onGlobalMediaUpdated)
  window.removeEventListener('keydown', onGlobalHomeKeydown)
  window.clearTimeout(searchTimer)
  window.clearTimeout(gridResizeTimer)
  gridObserver?.disconnect()
  document.removeEventListener('pointerdown', handleTagOutsidePointer)
})

const triggerMissingRecheck = async () => {
  if (!authState.user?.is_admin) return
  const now = Date.now()
  if (now - getLastMissingRecheckAt() < MISSING_RECHECK_COOLDOWN_MS) return
  setLastMissingRecheckAt(now)
  try {
    const res = await axios.post(`${API_BASE_URL}/system/recheck-missing`)
    if (!disposed && res.data.recovered > 0) {
      void fetchMedia()
    }
  } catch (err) {
    // silently ignore errors
  }
}

onMounted(async () => {
  window.addEventListener('he:media-updated', onGlobalMediaUpdated)
  window.addEventListener('keydown', onGlobalHomeKeydown)
  document.addEventListener('pointerdown', handleTagOutsidePointer)
  await nextTick()
  measurePageSize(false)
  if (containerRef.value && typeof ResizeObserver !== 'undefined') {
    gridObserver = new ResizeObserver(scheduleGridMeasurement)
    gridObserver.observe(containerRef.value)
  }
  await fetchMedia()
  await syncSelectedMediaFromRoute()
  void fetchTags()
  await triggerMissingRecheck()
})
</script>

<template>
  <div class="relative z-10 min-h-full">
    <PageHeader class="border-b border-line/80" :title="pageTitle" :count="loading && !totalItems ? undefined : `${totalItems.toLocaleString()} 项`">
      <template #actions>
        <div role="status" class="min-h-5 w-28 text-right text-meta text-subtle"><span v-if="delayedLoading">正在加载媒体…</span></div>
      </template>
      <p v-if="discardNotice" role="alert" class="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-meta text-warning">
        <span>文件清理未完成：{{ discardNotice }}</span>
        <router-link to="/discarded" class="font-medium text-accent-glow underline">查看丢弃记录</router-link>
        <button type="button" class="ml-auto underline focus-ring" @click="discardNotice = ''">关闭提示</button>
      </p>
      <p v-if="authState.user?.is_admin && hiddenDuplicatesCount > 0 && !hiddenDupNoticeDismissed" class="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface-2/80 px-3.5 py-2 text-meta text-subtle">
        <span>有 {{ hiddenDuplicatesCount }} 项媒体因待检或疑似重复暂未展示</span>
        <router-link to="/dedup" class="font-medium text-accent-glow underline">前往重复管理</router-link>
        <button type="button" class="ml-auto underline focus-ring" @click="hiddenDupNoticeDismissed = true">知道了</button>
      </p>

      <div class="he-filter-bar squircle flex flex-wrap items-center gap-2 rounded-2xl border border-line/85 bg-surface/80 p-2 shadow-[inset_0_1px_0_var(--he-border-specular)]">
        <div class="he-home-search flex min-w-0 flex-1 items-center gap-2" :class="compact ? 'w-full' : 'sm:max-w-lg'">
          <UiInput
            ref="searchInputRef"
            v-model="searchQuery"
            type="text"
            :size="compact ? 'lg' : 'md'"
            placeholder="搜索标题、作者、标签或推文… (按 / 聚焦)"
            aria-label="搜索标题或文件名"
            class="min-w-0 flex-1 pointer-coarse:[&_input]:min-h-11"
          >
            <template #leading><Search :size="16" /></template>
            <template v-if="searchQuery" #trailing>
              <UiIconButton label="清空搜索" size="sm" @click="searchQuery = ''"><X :size="14" aria-hidden="true" /></UiIconButton>
            </template>
          </UiInput>

          <button
            type="button"
            :class="iconButtonClass('secondary', compact ? 'lg' : 'md')"
            title="只看收藏"
            aria-label="只看收藏"
            :aria-pressed="favoriteOnly"
            @click="toggleFavoriteFilter"
          >
            <Star :size="compact ? 18 : 16" :class="favoriteOnly ? 'text-star' : ''" :fill="favoriteOnly ? 'currentColor' : 'none'" aria-hidden="true" />
          </button>

          <button
            v-if="compact"
            ref="filterTriggerRef"
            type="button"
            class="relative"
            :class="iconButtonClass('secondary', 'lg')"
            :aria-expanded="filtersExpanded"
            aria-controls="he-filter-drawer"
            title="展开筛选"
            aria-label="展开筛选"
            @click="filtersExpanded = !filtersExpanded"
          >
            <SlidersHorizontal :size="18" aria-hidden="true" />
            <span v-if="activeFilterCount" class="absolute -right-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1 text-caption font-medium text-on-accent tabular-nums">
              {{ activeFilterCount }}
            </span>
          </button>
        </div>

        <div v-if="!compact" class="ml-auto flex flex-wrap items-center gap-2">
          <div ref="tagDropdownRef" class="relative" @keydown.esc.prevent.stop="closeTagDropdown">
            <button
              ref="tagButtonRef"
              type="button"
              :class="[
                buttonClass('secondary', 'md'),
                'max-w-44 justify-between',
                hasTagFilter ? '!border-accent/50 !bg-accent/15 !text-accent-glow' : '',
              ]"
              :aria-expanded="tagDropdownOpen"
              aria-controls="he-tag-options"
              aria-label="按标签筛选"
              @click="tagDropdownOpen = !tagDropdownOpen"
            >
              <span class="flex min-w-0 items-center gap-1.5">
                <TagIcon :size="15" class="shrink-0" :class="hasTagFilter ? '' : 'text-subtle'" aria-hidden="true" />
                <span class="truncate">{{ selectedTagLabel }}</span>
              </span>
              <ChevronDown :size="15" class="shrink-0 text-subtle transition-transform duration-150" :class="tagDropdownOpen ? 'rotate-180' : ''" aria-hidden="true" />
            </button>
            <Transition name="he-pop">
            <div
              v-if="tagDropdownOpen"
              id="he-tag-options"
              :class="[popoverClass, 'absolute right-0 top-full z-50 mt-2 flex max-h-96 w-72 flex-col']"
            >
              <div class="space-y-1.5 p-1 pb-1.5">
                <input
                  ref="tagSearchRef"
                  v-model="tagSearchQuery"
                  type="text"
                  placeholder="过滤标签…"
                  aria-label="搜索标签"
                  :class="controlClass('sm')"
                  @click.stop
                />
                <div v-if="availableNamespaces.length" class="flex flex-wrap gap-1">
                  <button
                    type="button"
                    class="rounded-lg px-2 py-0.5 text-caption transition-colors"
                    :class="!dropdownNamespace && !selectedNamespace ? 'bg-accent/20 text-accent-glow font-medium' : 'bg-surface-2 text-subtle hover:text-ink'"
                    @click.stop="toggleNamespaceFilter('')"
                  >全部类</button>
                  <button
                    v-for="ns in availableNamespaces"
                    :key="ns.value"
                    type="button"
                    class="rounded-lg px-2 py-0.5 text-caption transition-colors"
                    :class="selectedNamespace === ns.value ? 'bg-accent/20 text-accent-glow font-medium' : 'bg-surface-2 text-subtle hover:text-ink'"
                    :title="`按 ${ns.label} 分类筛选`"
                    @click.stop="toggleNamespaceFilter(ns.value)"
                  >{{ ns.label }}</button>
                </div>
                <div v-if="includedTags.length > 1" class="flex items-center justify-between rounded-xl bg-surface-2 px-2.5 py-1 text-caption text-subtle">
                  <span>多标签匹配</span>
                  <div class="flex gap-1">
                    <button
                      type="button"
                      class="rounded-md px-1.5 py-0.5 transition-colors"
                      :class="tagMode === 'all' ? 'bg-accent text-on-accent font-medium' : 'hover:text-ink'"
                      @click.stop="tagMode = 'all'"
                    >全部(AND)</button>
                    <button
                      type="button"
                      class="rounded-md px-1.5 py-0.5 transition-colors"
                      :class="tagMode === 'any' ? 'bg-accent text-on-accent font-medium' : 'hover:text-ink'"
                      @click.stop="tagMode = 'any'"
                    >任一(OR)</button>
                  </div>
                </div>
              </div>
              <div class="custom-scrollbar min-h-0 flex-1 space-y-0.5 overflow-y-auto">
                <button type="button" :class="[menuItemClass, !hasTagFilter ? '!text-ink font-medium' : '']" @click="clearTagFilters()">
                  <span class="truncate">全部标签</span>
                  <Check v-if="!hasTagFilter" :size="15" class="ml-auto shrink-0 text-accent" aria-hidden="true" />
                </button>
                <div
                  v-for="tag in filteredTags"
                  :key="tag.id"
                  class="flex items-center gap-1 pr-1"
                >
                  <button
                    type="button"
                    :class="[menuItemClass, 'min-w-0 flex-1', includedTags.includes(tag.name) ? '!text-ink font-medium' : excludedTags.includes(tag.name) ? 'text-danger line-through' : '']"
                    @click="toggleIncludeTag(tag.name)"
                  >
                    <span class="truncate">{{ tag.name }}</span>
                    <span v-if="tag.namespace && tag.namespace !== 'general'" class="shrink-0 rounded bg-surface-3 px-1 text-[10px] text-subtle">{{ formatNamespaceLabel(tag.namespace) }}</span>
                    <Check v-if="includedTags.includes(tag.name)" :size="15" class="ml-auto shrink-0 text-accent" aria-hidden="true" />
                    <span v-else-if="tag.count" class="ml-auto shrink-0 text-caption text-subtle tabular-nums">{{ tag.count }}</span>
                  </button>
                  <button
                    type="button"
                    class="grid size-7 shrink-0 place-items-center rounded-lg transition-colors focus-ring"
                    :class="excludedTags.includes(tag.name) ? 'bg-danger/20 text-danger' : 'text-subtle hover:bg-surface-3 hover:text-danger'"
                    :title="`排除标签 ${tag.name}`"
                    :aria-label="`排除标签 ${tag.name}`"
                    :aria-pressed="excludedTags.includes(tag.name)"
                    @click.stop="toggleExcludeTag(tag.name)"
                  >
                    <Ban :size="13" aria-hidden="true" />
                  </button>
                </div>
                <p v-if="filteredTags.length === 0" class="py-3 text-center text-meta text-subtle">无匹配标签</p>
              </div>
            </div>
            </Transition>
          </div>

          <div class="flex items-center gap-1">
            <div ref="sortDropdownRef" class="relative" @keydown.esc.prevent.stop="sortDropdownOpen = false; sortButtonRef?.focus()">
              <button
                ref="sortButtonRef"
                type="button"
                :class="buttonClass('ghost', 'md')"
                aria-haspopup="menu"
                :aria-expanded="sortDropdownOpen"
                :aria-label="`排序方式：${sortLabel}`"
                @click="sortDropdownOpen = !sortDropdownOpen"
              >
                <ArrowUpDown :size="15" class="text-subtle" aria-hidden="true" />
                <span>{{ sortLabel }}</span>
                <ChevronDown :size="15" class="text-subtle transition-transform duration-150" :class="sortDropdownOpen ? 'rotate-180' : ''" aria-hidden="true" />
              </button>
              <Transition name="he-pop">
              <div v-if="sortDropdownOpen" role="menu" aria-label="排序方式" :class="[popoverClass, 'absolute right-0 top-full z-50 mt-2 min-w-44']">
                <button
                  v-for="option in sortOptions"
                  :key="option.value"
                  type="button"
                  role="menuitemradio"
                  :aria-checked="sortBy === option.value"
                  :class="[menuItemClass, sortBy === option.value ? '!text-ink font-medium' : '']"
                  @click="selectSort(option.value)"
                >
                  {{ option.label }}
                  <Check v-if="sortBy === option.value" :size="15" class="ml-auto text-accent" aria-hidden="true" />
                </button>
              </div>
              </Transition>
            </div>
            <UiButton v-if="sortBy === 'random'" variant="ghost" size="sm" title="换一批随机顺序" aria-label="换一批随机顺序" @click="reshuffleRandom">
              <template #icon><Shuffle :size="14" aria-hidden="true" /></template>
              换一批
            </UiButton>
          </div>

          <button
            ref="filterTriggerRef"
            type="button"
            :class="[
              buttonClass('secondary', 'md'),
              advancedFilterCount > 0 ? '!border-accent/50 !bg-accent/14 !text-accent-glow' : '',
            ]"
            :aria-expanded="filtersExpanded"
            aria-controls="he-filter-drawer"
            aria-label="打开筛选与布局面板"
            @click="filtersExpanded = !filtersExpanded"
          >
            <SlidersHorizontal :size="15" aria-hidden="true" />
            <span>筛选</span>
            <span v-if="advancedFilterCount > 0" class="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-accent px-1.5 text-[11px] font-semibold text-on-accent tabular-nums">
              {{ advancedFilterCount }}
            </span>
          </button>

          <UiSegmented v-model="viewModeModel" label="媒体显示视图" :options="viewSegments" />
        </div>
      </div>

      <!-- Universal Slide-Over Filter Drawer (Desktop right-side drawer + Mobile bottom sheet) -->
      <Teleport to="body">
        <Transition name="he-backdrop">
          <div
            v-if="filtersExpanded"
            class="fixed inset-0 z-[110] bg-black/55 backdrop-blur-[2px]"
            aria-hidden="true"
            @click="filtersExpanded = false"
          ></div>
        </Transition>
        <Transition name="he-drawer">
          <div
            v-if="filtersExpanded"
            id="he-filter-drawer"
            ref="filterPanelRef"
            role="dialog"
            :aria-modal="true"
            aria-label="媒体筛选和排序"
            :class="compact
              ? 'he-mobile-filters squircle flex flex-col gap-5 rounded-t-3xl border-t border-line-strong glass-elevated px-4 pt-3 shadow-modal'
              : 'he-desktop-drawer fixed inset-y-0 right-0 z-[120] flex w-full max-w-[400px] flex-col border-l border-line-strong glass-elevated shadow-modal'"
            :style="compact && drawerDragY ? { transform: `translateY(${drawerDragY}px)`, transition: 'none' } : undefined"
            @keydown="filterKeydown"
          >
            <div
              v-if="compact"
              class="-mx-4 -mt-3 flex justify-center pt-3 pb-1 touch-none"
              aria-hidden="true"
              @touchstart.passive="onDrawerTouchStart"
              @touchmove.passive="onDrawerTouchMove"
              @touchend.passive="onDrawerTouchEnd"
              @touchcancel.passive="onDrawerTouchEnd"
            >
              <span class="h-1 w-10 shrink-0 rounded-full bg-line-strong"></span>
            </div>
            <div
              class="flex shrink-0 items-center justify-between gap-3"
              :class="compact ? '' : 'border-b border-line/80 px-5 py-4'"
              @touchstart.passive="onDrawerTouchStart"
              @touchmove.passive="onDrawerTouchMove"
              @touchend.passive="onDrawerTouchEnd"
              @touchcancel.passive="onDrawerTouchEnd"
            >
              <div>
                <h2 class="text-heading font-semibold text-ink">筛选与布局</h2>
                <p v-if="!compact" class="mt-0.5 text-caption text-subtle">调节浏览密度，或按标签、来源与评分精简视图</p>
              </div>
              <button type="button" :class="iconButtonClass('ghost', compact ? 'lg' : 'md')" aria-label="关闭筛选" title="关闭筛选" @click="filtersExpanded = false">
                <X :size="20" aria-hidden="true" />
              </button>
            </div>

          <div class="custom-scrollbar min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-contain" :class="compact ? '' : 'px-5 py-5'">
            <div>
              <p class="mb-2 flex items-center gap-1.5 text-meta font-medium text-muted">
                <Layers :size="14" class="text-subtle" aria-hidden="true" />
                <span>布局舒适度</span>
              </p>
              <UiSegmented v-model="densityModel" label="布局舒适度" :options="densityOptions" block />
            </div>

            <div v-if="compact">
              <p class="mb-2 text-meta font-medium text-muted">显示方式</p>
              <UiSegmented v-model="viewModeModel" label="媒体显示视图" :options="viewSegments" block />
            </div>

            <div v-if="compact">
              <p class="mb-2 text-meta font-medium text-muted">排序</p>
              <UiSegmented v-model="sortBy" label="排序方式" :options="sortOptions" block />
              <UiButton v-if="sortBy === 'random'" variant="secondary" size="md" block class="mt-2" @click="reshuffleRandom">
                <template #icon><Shuffle :size="15" aria-hidden="true" /></template>
                换一批随机顺序
              </UiButton>
            </div>

            <div>
              <p class="mb-2 text-meta font-medium text-muted">来源</p>
              <UiSegmented v-model="sourceFilter" label="来源筛选" :options="sourceOptions" block />
            </div>

            <div>
              <p class="mb-2 flex items-center gap-1.5 text-meta font-medium text-muted">
                <Eye :size="14" class="text-subtle" aria-hidden="true" />
                <span>观看状态</span>
              </p>
              <UiSegmented v-model="viewStatusFilter" label="观看状态" :options="viewStatusOptions" block />
            </div>

            <div>
              <p class="mb-2 flex items-center gap-1.5 text-meta font-medium text-muted">
                <Star :size="14" class="text-subtle" aria-hidden="true" />
                <span>最低评分</span>
              </p>
              <UiSegmented v-model="minRatingFilter" label="最低评分" :options="ratingOptions" block />
            </div>

            <div>
              <div class="mb-2 flex items-center justify-between gap-2">
                <p class="flex items-center gap-1.5 text-meta font-medium text-muted">
                  <TagIcon :size="14" class="text-subtle" aria-hidden="true" />
                  <span>标签筛选</span>
                  <span v-if="hasTagFilter" class="text-caption text-accent-glow">({{ selectedTagLabel }})</span>
                </p>
                <button
                  v-if="hasTagFilter"
                  type="button"
                  class="text-caption text-subtle underline hover:text-ink focus-ring"
                  @click="clearTagFilters()"
                >清空标签</button>
              </div>
              <div class="rounded-2xl border border-line bg-surface/80 p-2.5">
                <div class="space-y-2 pb-2">
                  <input
                    v-model="tagSearchQuery"
                    type="text"
                    placeholder="过滤标签…"
                    aria-label="搜索标签"
                    :class="controlClass('sm')"
                  />
                  <div v-if="availableNamespaces.length" class="flex flex-wrap gap-1">
                    <button
                      type="button"
                      class="rounded-lg px-2 py-0.5 text-caption transition-colors"
                      :class="!selectedNamespace ? 'bg-accent/20 text-accent-glow font-medium' : 'bg-surface-2 text-subtle hover:text-ink'"
                      @click="toggleNamespaceFilter('')"
                    >全部类</button>
                    <button
                      v-for="ns in availableNamespaces"
                      :key="ns.value"
                      type="button"
                      class="rounded-lg px-2 py-0.5 text-caption transition-colors"
                      :class="selectedNamespace === ns.value ? 'bg-accent/20 text-accent-glow font-medium' : 'bg-surface-2 text-subtle hover:text-ink'"
                      :title="`按 ${ns.label} 分类筛选`"
                      @click="toggleNamespaceFilter(ns.value)"
                    >{{ ns.label }}</button>
                  </div>
                  <div v-if="includedTags.length > 1" class="flex items-center justify-between rounded-xl bg-surface-2 px-2.5 py-1 text-caption text-subtle">
                    <span>多标签匹配</span>
                    <div class="flex gap-1">
                      <button
                        type="button"
                        class="rounded-md px-1.5 py-0.5 transition-colors"
                        :class="tagMode === 'all' ? 'bg-accent text-on-accent font-medium' : 'hover:text-ink'"
                        @click="tagMode = 'all'"
                      >全部(AND)</button>
                      <button
                        type="button"
                        class="rounded-md px-1.5 py-0.5 transition-colors"
                        :class="tagMode === 'any' ? 'bg-accent text-on-accent font-medium' : 'hover:text-ink'"
                        @click="tagMode = 'any'"
                      >任一(OR)</button>
                    </div>
                  </div>
                </div>
                <div class="custom-scrollbar max-h-60 space-y-0.5 overflow-y-auto pr-0.5">
                  <div
                    v-for="tag in filteredTags"
                    :key="tag.id"
                    class="flex items-center gap-1"
                  >
                    <button
                      type="button"
                      :class="[menuItemClass, 'min-w-0 flex-1', includedTags.includes(tag.name) ? '!text-ink font-medium' : excludedTags.includes(tag.name) ? 'text-danger line-through' : '']"
                      @click="toggleIncludeTag(tag.name)"
                    >
                      <span class="truncate">{{ tag.name }}</span>
                      <span v-if="tag.namespace && tag.namespace !== 'general'" class="shrink-0 rounded bg-surface-3 px-1 text-[10px] text-subtle">{{ formatNamespaceLabel(tag.namespace) }}</span>
                      <Check v-if="includedTags.includes(tag.name)" :size="15" class="ml-auto shrink-0 text-accent" aria-hidden="true" />
                      <span v-else-if="tag.count" class="ml-auto shrink-0 text-caption text-subtle tabular-nums">{{ tag.count }}</span>
                    </button>
                    <button
                      type="button"
                      class="grid size-7 shrink-0 place-items-center rounded-lg transition-colors focus-ring"
                      :class="excludedTags.includes(tag.name) ? 'bg-danger/20 text-danger' : 'text-subtle hover:bg-surface-3 hover:text-danger'"
                      :title="`排除标签 ${tag.name}`"
                      :aria-label="`排除标签 ${tag.name}`"
                      :aria-pressed="excludedTags.includes(tag.name)"
                      @click="toggleExcludeTag(tag.name)"
                    >
                      <Ban :size="13" aria-hidden="true" />
                    </button>
                  </div>
                  <p v-if="filteredTags.length === 0" class="py-4 text-center text-meta text-subtle">无匹配标签</p>
                </div>
              </div>
            </div>
          </div>

          <div class="flex shrink-0 gap-2 pt-2" :class="compact ? '' : 'border-t border-line/80 px-5 py-4'">
            <UiButton v-if="activeFilterCount > 0" variant="secondary" :size="compact ? 'lg' : 'md'" @click="clearFilters">清除</UiButton>
            <UiButton variant="primary" :size="compact ? 'lg' : 'md'" block class="flex-1" @click="filtersExpanded = false">查看 {{ totalItems.toLocaleString() }} 项媒体</UiButton>
          </div>
          </div>
        </Transition>
      </Teleport>

      <nav v-if="compact" aria-label="媒体分类" class="he-media-categories he-scroll-fade-x -mx-4 mt-3 overflow-x-auto px-4 scrollbar-none">
        <div class="flex w-max gap-2">
          <router-link
            v-for="category in mobileCategories"
            :key="category.path"
            :to="{ path: category.path, query: { ...route.query, page: undefined, media: undefined } }"
            :aria-current="route.path === category.path ? 'page' : undefined"
            class="inline-flex min-h-10 shrink-0 items-center rounded-full border px-4 text-meta font-medium transition-colors duration-150 focus-ring"
            :class="route.path === category.path ? 'border-accent/50 bg-accent/15 text-accent-glow shadow-[inset_0_1px_0_rgb(255_255_255/0.08)]' : 'border-line bg-surface text-muted'"
          >{{ category.label }}</router-link>
        </div>
      </nav>

      <!-- Always-visible Active Filter Summary Bar -->
      <TransitionGroup v-if="activeFilterCount > 0" name="he-chip" tag="div" class="flex flex-wrap items-center gap-1.5 pt-3">
        <button
          v-if="searchQuery"
          key="chip-search"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/15 px-2.5 py-0.5 text-caption text-accent-glow transition-colors hover:bg-accent/25 focus-ring"
          @click="searchQuery = ''"
        >
          <span>搜索: {{ searchQuery }}</span>
          <X :size="12" aria-hidden="true" />
        </button>
        <button
          v-if="favoriteOnly"
          key="chip-fav"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-star/40 bg-star/12 px-2.5 py-0.5 text-caption text-star transition-colors hover:bg-star/20 focus-ring"
          @click="toggleFavoriteFilter"
        >
          <span>仅收藏</span>
          <X :size="12" aria-hidden="true" />
        </button>
        <button
          v-if="sortBy !== 'date'"
          key="chip-sort"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-line-strong bg-surface-2 px-2.5 py-0.5 text-caption text-ink transition-colors hover:bg-surface-3 focus-ring"
          @click="sortBy = 'date'"
        >
          <span>排序: {{ sortLabel }}</span>
          <X :size="12" aria-hidden="true" />
        </button>
        <button
          v-if="sourceFilter"
          key="chip-source"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/15 px-2.5 py-0.5 text-caption text-accent-glow transition-colors hover:bg-accent/25 focus-ring"
          @click="sourceFilter = ''"
        >
          <span>来源: {{ sourceLabel }}</span>
          <X :size="12" aria-hidden="true" />
        </button>
        <button
          v-if="viewStatusFilter"
          key="chip-status"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/15 px-2.5 py-0.5 text-caption text-accent-glow transition-colors hover:bg-accent/25 focus-ring"
          @click="viewStatusFilter = ''"
        >
          <span>状态: {{ viewStatusLabel }}</span>
          <X :size="12" aria-hidden="true" />
        </button>
        <button
          v-if="minRatingFilter"
          key="chip-rating"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/15 px-2.5 py-0.5 text-caption text-accent-glow transition-colors hover:bg-accent/25 focus-ring"
          @click="minRatingFilter = ''"
        >
          <span>评分: {{ minRatingLabel }}</span>
          <X :size="12" aria-hidden="true" />
        </button>
        <button
          v-if="selectedNamespace"
          key="chip-ns"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/15 px-2.5 py-0.5 text-caption text-accent-glow transition-colors hover:bg-accent/25 focus-ring"
          @click="selectedNamespace = ''; dropdownNamespace = ''"
        >
          <span>分类: {{ formatNamespaceLabel(selectedNamespace) }}</span>
          <X :size="12" aria-hidden="true" />
        </button>
        <button
          v-for="tag in includedTags"
          :key="`inc-${tag}`"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/15 px-2.5 py-0.5 text-caption text-accent-glow transition-colors hover:bg-accent/25 focus-ring"
          @click="toggleIncludeTag(tag)"
        >
          <span>+ {{ tag }}</span>
          <X :size="12" aria-hidden="true" />
        </button>
        <button
          v-for="tag in excludedTags"
          :key="`exc-${tag}`"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-danger/40 bg-danger/15 px-2.5 py-0.5 text-caption text-danger transition-colors hover:bg-danger/25 focus-ring"
          @click="toggleExcludeTag(tag)"
        >
          <span>- {{ tag }}</span>
          <X :size="12" aria-hidden="true" />
        </button>
        <UiButton key="chip-clear" variant="ghost" size="sm" class="ml-auto" @click="clearFilters">
          <template #icon><X :size="14" aria-hidden="true" /></template>
          清除筛选
        </UiButton>
      </TransitionGroup>
    </PageHeader>

    <section v-if="featuredContinue && !searchQuery && !hasTagFilter" class="page-gutter mt-6" aria-label="今晚继续">
      <div class="page-container">
        <div class="he-hero-spotlight relative overflow-hidden rounded-3xl border border-line bg-surface shadow-[var(--he-shadow-card),inset_0_1px_0_var(--he-border-specular)]">
          <img
            v-if="featuredContinue.cover_path"
            :src="thumbnailUrl(featuredContinue.cover_path)"
            alt=""
            aria-hidden="true"
            class="pointer-events-none absolute inset-0 h-full w-full scale-110 object-cover opacity-20 blur-xl"
          />
          <div class="he-hero-scrim pointer-events-none absolute inset-0"></div>

          <div class="he-hero-inner relative z-10 grid">
            <button type="button" class="he-hero-media group relative min-h-48 overflow-hidden bg-surface-2 text-left focus-ring" :aria-label="`打开媒体：${featuredContinue.title}`" @click="openMedia(featuredContinue)">
              <img :src="featuredContinue.cover_path ? thumbnailUrl(featuredContinue.cover_path) : mediaPlaceholderUrl" :alt="featuredContinue.title" fetchpriority="high" loading="eager" class="absolute inset-0 h-full w-full object-cover transition-transform duration-300 group-hover:scale-105" />
              <span class="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent"></span>
              <span class="absolute bottom-3 left-3 inline-flex items-center gap-1.5 rounded-full bg-black/75 px-3 py-1.5 text-caption font-medium text-white ring-1 ring-inset ring-white/15"><Play :size="13" fill="currentColor" aria-hidden="true" />继续</span>
            </button>
            <div class="he-hero-body flex min-w-0 flex-col justify-center gap-3">
              <p class="inline-flex w-fit items-center gap-1.5 rounded-full border border-accent/30 bg-accent/12 px-2.5 py-0.5 text-[11px] font-medium tracking-wide text-accent-glow">
                今晚继续 · {{ continueTitle }}
              </p>
              <h2 class="he-hero-title line-clamp-2 font-semibold leading-tight text-ink">{{ featuredContinue.title }}</h2>
              <p class="flex min-h-5 min-w-0 flex-wrap items-center gap-2 text-meta text-subtle tabular-nums">
                <span class="rounded-md bg-surface-2 px-2 py-0.5 text-caption font-medium text-muted">{{ typeLabel(featuredContinue.media_type) }}</span>
                <span v-if="continueMeta(featuredContinue)">{{ continueMeta(featuredContinue) }}</span>
                <span v-if="featuredContinue.rating" class="text-star">★ {{ featuredContinue.rating }}</span>
                <span v-if="featuredContinue.tags?.length" class="truncate text-muted">{{ featuredContinue.tags.slice(0, 3).map(tag => tag.name).join(' · ') }}</span>
              </p>
              <div :class="{ invisible: progressPercent(featuredContinue) === 0 }" :aria-hidden="progressPercent(featuredContinue) === 0" class="h-1.5 w-full max-w-md overflow-hidden rounded-full bg-surface-3" role="progressbar" :aria-label="`${featuredContinue.title}观看进度`" :aria-valuenow="progressPercent(featuredContinue)" aria-valuemin="0" aria-valuemax="100">
                <div class="h-full rounded-full bg-accent shadow-[0_0_10px_rgb(var(--color-accent)/0.7)]" :style="{ width: `${progressPercent(featuredContinue)}%` }"></div>
              </div>
              <div class="flex flex-wrap gap-2.5 pt-1">
                <UiButton variant="primary" @click="openMedia(featuredContinue)"><template #icon><Play :size="15" fill="currentColor" aria-hidden="true" /></template>继续{{ featuredContinue.media_type === 'manga' ? '阅读' : featuredContinue.media_type === 'audio' ? '收听' : '观看' }}</UiButton>
                <UiButton v-if="recentlyOpened.length > 1" variant="secondary" @click="showOtherContinueItems">看看其他继续项</UiButton>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="otherContinueItems.length > 0 && !searchQuery && !hasTagFilter" ref="continueSectionRef" class="page-gutter mt-6 select-none" aria-label="继续观看">
      <div class="page-container">
        <SectionHeader :title="continueTitle">
          <template #actions>
            <UiButton variant="ghost" size="sm" :title="continueCollapsed ? '展开继续观看' : '收起继续观看'" :aria-expanded="!continueCollapsed" @click="continueCollapsed = !continueCollapsed">
              {{ continueCollapsed ? '展开' : '收起' }}
              <template #trailing><ChevronDown :size="14" class="transition-transform duration-150" :class="{ '-rotate-90': continueCollapsed }" aria-hidden="true" /></template>
            </UiButton>
            <span v-if="!compact" class="flex items-center gap-2 transition-opacity duration-150" :class="continueCollapsed ? 'invisible pointer-events-none opacity-0' : 'opacity-100'" :inert="continueCollapsed" :aria-hidden="continueCollapsed">
              <UiIconButton label="向左滚动" variant="secondary" size="sm" @click="scrollContinue(-1)"><ChevronLeft :size="16" aria-hidden="true" /></UiIconButton>
              <UiIconButton label="向右滚动" variant="secondary" size="sm" @click="scrollContinue(1)"><ChevronRight :size="16" aria-hidden="true" /></UiIconButton>
            </span>
          </template>
        </SectionHeader>
        <div class="he-continue-reveal" :class="{ 'is-expanded': !continueCollapsed }" :inert="continueCollapsed" :aria-hidden="continueCollapsed">
        <div class="he-continue-reveal-clip">
        <div ref="continueScrollRef" class="he-scroll-fade-x -mx-4 flex gap-3 overflow-x-auto px-4 scrollbar-none sm:-mx-6 sm:px-6 lg:mx-0 lg:px-0" :class="continueDragging ? 'cursor-grabbing' : 'cursor-grab'" @pointerdown="startContinueDrag" @pointermove="moveContinueDrag" @pointerup="endContinueDrag" @pointercancel="endContinueDrag" @lostpointercapture="endContinueDrag" @click.capture="preventDraggedClick" @dragstart.prevent>
          <div
            v-for="item in otherContinueItems"
            :key="item.id"
            class="group relative flex w-72 shrink-0 items-center gap-3 rounded-2xl squircle border border-line bg-surface p-2.5 shadow-[inset_0_1px_0_var(--he-border-specular)] transition-[background-color,border-color,translate] duration-150 ease-out hover:-translate-y-0.5 hover:border-line-strong hover:bg-surface-2"
          >
            <button
              type="button"
              class="absolute inset-0 z-10 rounded-2xl focus-ring"
              :aria-label="`打开媒体：${item.title}`"
              @click="openMedia(item)"
            ></button>
            <div class="relative h-16 shrink-0 overflow-hidden rounded-xl bg-surface-2 ring-1 ring-inset ring-white/8" :class="continueThumbClass(item)">
              <img :src="item.cover_path ? thumbnailUrl(item.cover_path) : mediaPlaceholderUrl" alt="" class="h-full w-full object-cover" />
            </div>
            <div class="min-w-0 flex-1">
              <h3 class="line-clamp-2 pr-6 text-meta font-medium leading-snug text-ink pointer-coarse:pr-8" :title="item.title">{{ item.title }}</h3>
              <p class="mt-1 flex min-w-0 items-center gap-1.5 text-caption text-subtle tabular-nums">
                <span class="shrink-0">{{ typeLabel(item.media_type) }}</span>
                <template v-if="continueMeta(item)">
                  <span class="text-faint" aria-hidden="true">·</span>
                  <span class="truncate">{{ continueMeta(item) }}</span>
                </template>
              </p>
              <div
                v-if="progressPercent(item) > 0"
                class="mt-2 h-1 overflow-hidden rounded-sm bg-surface-3"
                role="progressbar"
                :aria-label="`${item.title}观看进度`"
                :aria-valuenow="progressPercent(item)"
                aria-valuemin="0"
                aria-valuemax="100"
              >
                <div class="h-full rounded-sm bg-accent" :style="{ width: `${progressPercent(item)}%` }"></div>
              </div>
            </div>
            <button
              type="button"
              class="he-continue-dismiss absolute right-1 top-1 z-20 grid size-7 place-items-center rounded-lg text-subtle transition-colors duration-150 hover:bg-surface-3 hover:text-ink focus-ring pointer-coarse:size-10"
              title="从列表中移除"
              :aria-label="`从继续观看中移除：${item.title}`"
              @click="dismissContinueItem(item.id, $event)"
            >
              <X :size="14" aria-hidden="true" />
            </button>
          </div>
        </div>
        </div>
        </div>
      </div>
    </section>

    <div ref="containerRef" class="page-gutter pb-12" :class="(featuredContinue || otherContinueItems.length > 0) && !searchQuery && !hasTagFilter ? 'mt-7' : 'mt-6'">
      <div class="page-container">
        <div v-if="loading && !mediaList.length" data-media-grid :class="viewMode === 'list' ? 'flex flex-col gap-2' : viewMode === 'wide' ? 'grid grid-cols-1 gap-x-5 gap-y-7 md:grid-cols-2 xl:grid-cols-3' : viewMode === 'poster' ? posterGridClass : 'poster-grid'">
          <template v-if="viewMode === 'list'">
            <UiSkeleton v-for="i in 8" :key="i" class="h-24 w-full rounded-2xl" />
          </template>
          <div v-for="i in 12" v-else :key="i">
            <UiSkeleton class="w-full rounded-2xl" :class="skeletonAspect" />
            <UiSkeleton shape="text" class="mt-3 w-4/5" />
            <UiSkeleton shape="text" class="mt-2 w-1/2" />
          </div>
        </div>

        <EmptyState v-else-if="mediaError" :icon="TriangleAlert" tone="danger" title="媒体列表加载失败" :description="mediaError">
          <UiButton variant="secondary" size="sm" @click="fetchMedia()">重试</UiButton>
        </EmptyState>

        <div v-else-if="mediaList.length > 0" class="relative flex flex-col gap-10" :aria-busy="loading">
          <div :inert="loading">
          <div v-if="displayedView === 'poster'" data-media-grid :class="[posterGridClass, 'he-stagger-grid']">
            <div
              v-for="(item, index) in mediaList"
              :key="item.id"
              v-memo="[item.id, item.cover_path, item.title, item.favorite, item.rating, item.view_status, item.progress, item.is_missing, displayedType, authState.user?.is_admin]"
              class="he-media-actions relative min-w-0"
            >
              <MediaCard :media="item" :index="index" :shape="cardShape" :show-type="!displayedType" @click="openMedia(item)" />
              <button v-if="authState.user?.is_admin" type="button" class="he-media-delete absolute right-2 z-10 grid size-9 pointer-coarse:size-11 place-items-center rounded-xl bg-black/78 text-white/90 ring-1 ring-inset ring-white/15 transition-colors hover:bg-danger hover:text-white focus-ring" :class="!displayedType ? 'top-10' : 'top-2'" :aria-label="`删除并丢弃 ${item.title}`" title="删除并丢弃" @click.stop="discardTarget = { kind: 'media', target_id: item.id }"><Trash2 :size="16" aria-hidden="true" /></button>
            </div>
          </div>
          <div v-else data-media-grid :class="displayedView === 'masonry' ? 'masonry-grid' : displayedView === 'wide' ? 'he-wide-grid he-stagger-grid' : 'he-stagger-list flex flex-col gap-2.5'">
            <div v-for="item in mediaList" :key="item.id" class="he-media-actions relative min-w-0" :class="displayedView === 'masonry' ? 'masonry-grid-item' : displayedView === 'list' ? 'flex items-center gap-2' : ''">
              <MediaViewCard :media="item" :mode="displayedView" :class="displayedView === 'list' ? 'min-w-0 flex-1' : ''" @click="openMedia(item)" />
              <button v-if="authState.user?.is_admin" type="button" class="he-media-delete grid size-9 pointer-coarse:size-11 shrink-0 place-items-center rounded-xl transition-colors hover:bg-danger hover:text-white focus-ring" :class="displayedView === 'list' ? 'bg-surface text-subtle' : ['absolute right-2 z-10 bg-black/78 text-white/90 ring-1 ring-inset ring-white/15', displayedView === 'masonry' ? 'top-10' : 'top-2']" :aria-label="`删除并丢弃 ${item.title}`" title="删除并丢弃" @click.stop="discardTarget = { kind: 'media', target_id: item.id }"><Trash2 :size="16" aria-hidden="true" /></button>
            </div>
          </div>
          </div>

          <PaginationControl
            v-if="pageCount > 1"
            :page="currentPage"
            :page-count="pageCount"
            :total-items="totalItems"
            :page-size="pageSize"
            :disabled="loading"
            item-label="项媒体"
            @change="goToPage"
          />
        </div>

        <EmptyState v-else-if="!loading && mediaList.length === 0" :icon="Search" title="没有找到匹配的媒体" description="可以去设置页添加扫描目录，或调整当前筛选条件。">
          <UiButton v-if="activeFilterCount > 0" variant="secondary" size="sm" @click="clearFilters">清除筛选</UiButton>
        </EmptyState>
      </div>
    </div>

    <Teleport to="body">
      <UiToast v-if="openingError" :message="openingError" urgent overlay class="fixed bottom-6 left-1/2 z-[240] max-w-[90%] -translate-x-1/2" />
    </Teleport>
    <DiscardContentDialog v-model:target="discardTarget" @discarded="afterDiscard" />
    <MediaDetail
      v-if="selectedMedia"
      :initial-media="selectedMedia"
      :current-image-id="selectedMedia.media_type === 'image' ? Number(route.query.media) : undefined"
      :verified-for-open="true"
      :all-media="viewerMediaList"
      :has-adjacent-media-page="hasAdjacentViewerPage"
      :load-adjacent-media-page="loadAdjacentViewerPage"
      @close="closeMedia"
      @discarded="afterDiscard"
      @updated="updateMediaInList"
      @navigate="openMedia($event, true)"
    />
  </div>
</template>

<style scoped>
.he-hero-spotlight {
  container: hero / inline-size;
  contain: layout paint;
}

.he-hero-inner {
  grid-template-columns: 1fr;
}

.he-hero-body {
  padding: 20px;
}

.he-hero-title {
  font-size: clamp(1.125rem, 1rem + 1vw, 1.5625rem);
}

@supports (font-size: 1cqi) {
  .he-hero-title {
    font-size: clamp(1.125rem, 0.9rem + 1.5cqi, 1.5625rem);
  }
  .he-hero-body {
    padding: clamp(18px, 3cqi, 28px);
  }
}

@container hero (min-width: 580px) {
  .he-hero-inner {
    grid-template-columns: 240px 1fr;
    grid-template-columns: clamp(200px, 25cqi, 280px) minmax(0, 1fr);
    min-height: 172px;
  }
  .he-hero-media {
    min-height: 100%;
  }
}

.he-hero-scrim {
  background: linear-gradient(120deg var(--in-oklab), rgb(var(--color-surface) / 0.88) 0%, rgb(var(--color-surface) / 0.94) 55%, rgb(var(--color-surface) / 0.98) 100%);
}

/* Animate the space around the row, keeping cards at their intrinsic height.
   Native interpolation also reverses smoothly during repeated clicks. */
.he-continue-reveal {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 240ms cubic-bezier(.22, 1, .36, 1);
}
.he-continue-reveal.is-expanded { grid-template-rows: 1fr; }
.he-continue-reveal-clip {
  min-height: 0;
  overflow: hidden;
  opacity: 0;
  transition: opacity 160ms ease-out;
}
.he-continue-reveal.is-expanded > .he-continue-reveal-clip { opacity: 1; }
@media (prefers-reduced-motion: reduce) {
  .he-continue-reveal, .he-continue-reveal-clip { transition: none; }
}
@media (max-width: 899px) {
  .he-mobile-filters {
    position: fixed;
    inset: auto 0 0;
    z-index: 120;
    max-height: 85dvh;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding-left: max(16px, env(safe-area-inset-left));
    padding-right: max(16px, env(safe-area-inset-right));
    padding-bottom: calc(16px + env(safe-area-inset-bottom));
  }
}

.he-continue-dismiss {
  opacity: 1;
}

@media (hover: hover) and (pointer: fine) {
  .he-continue-dismiss {
    opacity: 0;
  }
  .group:hover .he-continue-dismiss,
  .group:focus-within .he-continue-dismiss {
    opacity: 1;
  }
}
</style>
