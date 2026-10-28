<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { ArrowUpDown, Check, ChevronDown, ChevronLeft, ChevronRight, Columns3, LayoutGrid, List, Play, Rows3, Search, SlidersHorizontal, Star, Tag as TagIcon, TriangleAlert, Trash2, X } from 'lucide-vue-next'
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
const compact = useCompactViewport()
const filterPanelRef = ref<HTMLElement | null>(null)
const filterTriggerRef = ref<HTMLButtonElement | null>(null)

const props = defineProps<{
  mediaType?: string
}>()

const route = useRoute()
const router = useRouter()
const mediaList = ref<Media[]>([])
const continueMedia = ref<Media[]>([])
const tags = ref<Tag[]>([])
const loading = ref(true)
const mediaError = ref(''), openingMedia = ref(false), openingError = ref('')
const discardTarget = ref<DiscardTarget | null>(null)
const discardNotice = ref('')
const afterDiscard = async (record: DiscardRecord) => {
  discardNotice.value = record.cleanup_error || ''
  closeMedia(); await fetchMedia(); await fetchContinueMedia()
}
const selectedMedia = ref<Media | null>(null)
const searchQuery = ref(typeof route.query.search === 'string' ? route.query.search : '')
const validSort = (value: unknown): 'date' | 'title' | 'rating' | 'opened' => value === 'title' || value === 'rating' || value === 'opened' ? value : 'date'
const sortBy = ref(validSort(route.query.sort))
const selectedTag = ref(typeof route.query.tag === 'string' ? route.query.tag : '')
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

const filteredTags = computed(() => {
  const query = tagSearchQuery.value.trim().toLowerCase()
  if (!query) return tags.value
  return tags.value.filter(tag => tag.name.toLowerCase().includes(query))
})

const activeFilterCount = computed(() => {
  return Number(Boolean(selectedTag.value)) +
    Number(Boolean(sourceFilter.value)) +
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
  delete query.sort
  delete query.source
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
  const header = section.parentElement?.querySelector<HTMLElement>('[data-library-header]')
  section.style.scrollMarginTop = `${(header?.offsetHeight ?? 0) + 16}px`
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
  props.mediaType === 'manga' ? '继续阅读' : props.mediaType === 'audio' ? '继续收听' : props.mediaType === 'image' ? '最近浏览' : '继续观看')

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
  tag: selectedTag.value || undefined,
  favorite: favoriteOnly.value ? true : undefined,
  source_site: sourceFilter.value || undefined,
  sort: sortBy.value,
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

const selectedTagLabel = computed(() => selectedTag.value || '全部标签')

type SortKey = 'date' | 'title' | 'rating' | 'opened'
const sortOptions: SegmentedOption<SortKey>[] = [
  { value: 'date', label: '最近添加' },
  { value: 'opened', label: '最近打开' },
  { value: 'rating', label: '评分' },
  { value: 'title', label: '名称' },
]
const sortLabel = computed(() => sortOptions.find(option => option.value === sortBy.value)?.label ?? '最近添加')
const sourceOptions: SegmentedOption<'' | 'x' | 'wnacg' | 'local'>[] = [
  { value: '', label: '全部来源' },
  { value: 'local', label: '本地' },
  { value: 'x', label: 'X' },
  { value: 'wnacg', label: 'WNACG' },
]
const viewSegments = computed<SegmentedOption<MediaViewMode>[]>(() => viewOptions.value.map(option => ({
  value: option.mode, label: option.label, icon: option.icon, iconOnly: !compact.value,
})))
const viewModeModel = computed<MediaViewMode>({
  get: () => viewMode.value,
  set: mode => selectViewMode(mode),
})

// Single-type pages show each type's own aspect ratio; the mixed wall keeps uniform posters.
const cardShape = computed(() => props.mediaType && props.mediaType !== 'image' ? 'natural' : 'poster')
const posterGridClass = computed(() => props.mediaType === 'video' && cardShape.value === 'natural'
  ? 'grid grid-cols-1 gap-x-5 gap-y-7 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4'
  : 'poster-grid')
const skeletonAspect = computed(() => viewMode.value === 'wide' || (viewMode.value === 'poster' && props.mediaType === 'video')
  ? 'aspect-video'
  : viewMode.value === 'poster' && props.mediaType === 'audio' ? 'aspect-square' : 'aspect-[2/3]')

const measurePageSize = (refresh = true) => {
  if (route.query.media || openingMedia.value || selectedMedia.value) { pendingGridMeasurement = true; return }
  pendingGridMeasurement = false
  const grid = containerRef.value?.querySelector<HTMLElement>('[data-media-grid]')
  let columns = 1
  if ((viewMode.value === 'poster' || viewMode.value === 'wide') && grid) {
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
  sortBy.value = value
  sortDropdownOpen.value = false
  sortButtonRef.value?.focus()
}

const selectTag = (tagName: string) => {
  selectedTag.value = tagName
  tagSearchQuery.value = ''
  tagDropdownOpen.value = false
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

const fetchContinueMedia = async () => {
  if (disposed) return
  const scope = requestScope('continue'), identity = authIdentity()
  try {
    const res = await axios.get<Media[]>(`${API_BASE_URL}/media`, {
      ...scope, params: { media_type: props.mediaType, sort: 'opened', ...(desktopBridge ? { view_status: 'viewing' } : {}), limit: 12, offset: 0 },
    })
    if (!disposed && !scope.signal.aborted && identity === authIdentity()) continueMedia.value = res.data
  } catch (err) {
    if (!disposed && !scope.signal.aborted && identity === authIdentity()) continueMedia.value = []
    if (!axios.isCancel(err)) console.error('Failed to fetch continue-watching media:', err)
  }
}

const fetchMedia = async (scrollBehavior: ScrollBehavior = 'auto') => {
  if (disposed) return
  const scope = requestScope('list'), identity = authIdentity()
  const requestId = ++mediaRequestId
  if (hasCompletedInitialFetch && scrollBehavior !== 'auto') scrollToTop(scrollBehavior)
  loading.value = true
  mediaError.value = ''
  try {
    const res = await axios.get<Media[]>(`${API_BASE_URL}/media`, { ...scope, params: mediaParamsForPage(currentPage.value) })
    if (disposed || scope.signal.aborted || identity !== authIdentity() || requestId !== mediaRequestId) return

    const headerTotal = Number(res.headers['x-total-count'])
    totalItems.value = Number.isSafeInteger(headerTotal) && headerTotal >= 0
      ? headerTotal
      : (currentPage.value - 1) * pageSize.value + res.data.length

    const lastPage = Math.max(1, Math.ceil(totalItems.value / pageSize.value))
    if (currentPage.value > lastPage) {
      currentPage.value = lastPage
      syncPageQuery(lastPage, true)
      await fetchMedia()
      return
    }
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

const updateMediaInList = (media: Media) => {
  const index = mediaList.value.findIndex(item => item.id === media.id)
  if (index >= 0) {
    mediaList.value[index] = media
  }
  const viewerIndex = viewerMediaList.value.findIndex(item => item.id === media.id)
  if (viewerIndex >= 0) viewerMediaList.value[viewerIndex] = media
  const continueIndex = continueMedia.value.findIndex(item => item.id === media.id)
  if (continueIndex >= 0) {
    continueMedia.value[continueIndex] = media
  } else if (media.last_opened_at || progressPercent(media) > 0) {
    continueMedia.value = [media, ...continueMedia.value].slice(0, 12)
  }
  if (selectedMedia.value?.id === media.id) {
    selectedMedia.value = media
  }
  fetchTags()
}

const canKeepImageReader = (mediaId: number) => !desktopBridge && selectedMedia.value?.media_type === 'image'
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
  const current = [route.query.search || '', route.query.tag || '', validSort(route.query.sort), validSource(route.query.source)]
  const desired = [searchQuery.value, selectedTag.value, sortBy.value, sourceFilter.value]
  if (current.every((value, index) => value === desired[index])) return
  const query = { ...route.query }
  delete query.page
  for (const [key, value] of Object.entries({ search: searchQuery.value, tag: selectedTag.value, sort: sortBy.value === 'date' ? '' : sortBy.value, source: sourceFilter.value })) {
    if (value) query[key] = value
    else delete query[key]
  }
  void router.replace({ path: route.path, query })
}
watch(searchQuery, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(syncFilters, 250)
})
watch([selectedTag, sortBy, sourceFilter], syncFilters)
watch(() => props.mediaType, () => { void fetchContinueMedia() })
watch(() => JSON.stringify([props.mediaType, route.query.search, route.query.tag, route.query.sort, route.query.source, route.query.favorite, route.query.page]), () => {
  window.clearTimeout(searchTimer)
  searchQuery.value = typeof route.query.search === 'string' ? route.query.search : ''
  selectedTag.value = typeof route.query.tag === 'string' ? route.query.tag : ''
  sortBy.value = validSort(route.query.sort)
  sourceFilter.value = validSource(route.query.source)
  favoriteOnly.value = route.query.favorite === 'true'
  currentPage.value = routePage(route.query.page)
  void fetchMedia()
})
watch(filtersExpanded, async open => {
  if (!compact.value) return
  await nextTick()
  if (open) filterPanelRef.value?.querySelector<HTMLButtonElement>('button')?.focus()
  else filterTriggerRef.value?.focus()
})
const filterKeydown = (event: KeyboardEvent) => {
  if (!compact.value || !filtersExpanded.value) return
  if (event.key === 'Escape') { event.preventDefault(); filtersExpanded.value = false }
  if (event.key !== 'Tab') return
  const buttons = filterPanelRef.value?.querySelectorAll<HTMLElement>('button:not([disabled]), input, [tabindex="0"]')
  if (!buttons?.length) return
  const first = buttons[0]!, last = buttons[buttons.length - 1]!
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
const mobileCategories = [ { label: '全部', path: '/' }, { label: '漫画', path: '/type/manga' }, { label: '视频', path: '/type/video' }, { label: '音频', path: '/type/audio' }, { label: '图片', path: '/type/image' } ]
watch(() => route.query.media, () => {
  syncSelectedMediaFromRoute()
})
watch([viewMode, () => props.mediaType], async () => {
  await nextTick()
  scheduleGridMeasurement()
})
watch([selectedMedia, openingMedia, () => route.query.media], () => {
  if (pendingGridMeasurement && !selectedMedia.value && !openingMedia.value && !route.query.media) scheduleGridMeasurement()
})

const onGlobalMediaUpdated = (event: Event) => updateMediaInList((event as CustomEvent<Media>).detail)
const onOpeningKeydown = (event: KeyboardEvent) => {
  if (openingMedia.value && event.key === 'Escape') closeMedia()
}
onUnmounted(() => {
  disposed = true; ++mediaRequestId; ++detailRequestId; ++viewerPageRequestId
  for (const controller of controllers.values()) controller.abort()
  window.removeEventListener('he:media-updated', onGlobalMediaUpdated)
  window.removeEventListener('keydown', onOpeningKeydown)
  window.clearTimeout(searchTimer)
  window.clearTimeout(gridResizeTimer)
  gridObserver?.disconnect()
  document.removeEventListener('pointerdown', handleTagOutsidePointer)
})

const triggerMissingRecheck = async () => {
  if (!authState.user?.is_admin) return
  try {
    const res = await axios.post(`${API_BASE_URL}/system/recheck-missing`)
    if (res.data.recovered > 0) {
      fetchMedia()
    }
  } catch (err) {
    // silently ignore errors
  }
}

onMounted(async () => {
  window.addEventListener('he:media-updated', onGlobalMediaUpdated)
  window.addEventListener('keydown', onOpeningKeydown)
  document.addEventListener('pointerdown', handleTagOutsidePointer)
  await nextTick()
  measurePageSize(false)
  if (containerRef.value && typeof ResizeObserver !== 'undefined') {
    gridObserver = new ResizeObserver(scheduleGridMeasurement)
    gridObserver.observe(containerRef.value)
  }
  await Promise.all([fetchMedia(), fetchContinueMedia()])
  await syncSelectedMediaFromRoute()
  void fetchTags()
  await triggerMissingRecheck()
})
</script>

<template>
  <div class="relative z-10 min-h-full">
    <PageHeader sticky data-library-header :title="pageTitle" :count="loading && !totalItems ? undefined : `${totalItems.toLocaleString()} 项`">
      <p v-if="discardNotice" role="alert" class="w-full text-meta text-warning">文件清理未完成：{{ discardNotice }} <router-link to="/discarded" class="text-accent underline">查看丢弃记录</router-link> <button type="button" class="ml-2 underline focus-ring" @click="discardNotice = ''">关闭提示</button></p>
      <div class="flex flex-wrap items-center gap-2">
        <div class="he-home-search flex min-w-0 items-center gap-2" :class="compact ? 'w-full' : ''">
          <UiInput
            v-model="searchQuery"
            type="text"
            :size="compact ? 'lg' : 'md'"
            placeholder="搜索标题、文件名…"
            aria-label="搜索标题或文件名"
            :class="compact ? 'flex-1 pointer-coarse:[&_input]:h-11' : 'w-64 xl:w-72'"
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

        <Teleport to="body" :disabled="!compact">
          <div v-if="compact && filtersExpanded" class="fixed inset-0 z-[110] bg-black/60" aria-hidden="true" @click="filtersExpanded = false"></div>
          <div
            ref="filterPanelRef"
            :class="compact
              ? [filtersExpanded ? 'flex' : 'hidden', 'he-mobile-filters flex-col gap-5 rounded-t-3xl border-t border-line-strong bg-surface-3 px-4 pt-4 shadow-modal']
              : 'flex flex-wrap items-center gap-2'"
            :role="compact ? 'dialog' : undefined"
            :aria-modal="compact ? true : undefined"
            aria-label="媒体筛选和排序"
            @keydown="filterKeydown"
          >
            <div v-if="compact" class="flex items-center justify-between">
              <h2 class="text-heading font-semibold text-ink">筛选和排序</h2>
              <button type="button" :class="iconButtonClass('ghost', 'lg')" aria-label="关闭筛选" title="关闭筛选" @click="filtersExpanded = false">
                <X :size="20" aria-hidden="true" />
              </button>
            </div>

            <div>
              <p v-if="compact" class="mb-2 text-meta font-medium text-muted">标签</p>
              <div ref="tagDropdownRef" class="relative" @keydown.esc.prevent.stop="closeTagDropdown">
                <button
                  ref="tagButtonRef"
                  type="button"
                  :class="[
                    buttonClass('secondary', compact ? 'lg' : 'md', compact),
                    'justify-between',
                    compact ? '' : 'max-w-52',
                    selectedTag ? '!border-accent/50 !bg-accent/15 !text-accent-glow' : '',
                  ]"
                  :aria-expanded="tagDropdownOpen"
                  aria-controls="he-tag-options"
                  aria-label="按标签筛选"
                  @click="tagDropdownOpen = !tagDropdownOpen"
                >
                  <span class="flex min-w-0 items-center gap-2">
                    <TagIcon :size="15" class="shrink-0" :class="selectedTag ? '' : 'text-subtle'" aria-hidden="true" />
                    <span class="truncate">{{ selectedTagLabel }}</span>
                  </span>
                  <ChevronDown :size="15" class="shrink-0 text-subtle transition-transform duration-150" :class="tagDropdownOpen ? 'rotate-180' : ''" aria-hidden="true" />
                </button>
                <div
                  v-if="tagDropdownOpen"
                  id="he-tag-options"
                  :class="[popoverClass, compact ? 'mt-2 w-full' : 'absolute left-0 top-full z-50 mt-1.5 w-64']"
                  class="flex max-h-80 flex-col"
                >
                  <div class="p-1 pb-1.5">
                    <input
                      ref="tagSearchRef"
                      v-model="tagSearchQuery"
                      type="text"
                      placeholder="过滤标签…"
                      aria-label="搜索标签"
                      :class="controlClass('sm')"
                      @click.stop
                    />
                  </div>
                  <div class="custom-scrollbar min-h-0 flex-1 space-y-0.5 overflow-y-auto">
                    <button type="button" :class="[menuItemClass, selectedTag === '' ? '!text-ink font-medium' : '']" @click="selectTag('')">
                      <span class="truncate">全部标签</span>
                      <Check v-if="selectedTag === ''" :size="15" class="ml-auto shrink-0 text-accent" aria-hidden="true" />
                    </button>
                    <button
                      v-for="tag in filteredTags"
                      :key="tag.id"
                      type="button"
                      :class="[menuItemClass, selectedTag === tag.name ? '!text-ink font-medium' : '']"
                      @click="selectTag(tag.name)"
                    >
                      <span class="truncate">{{ tag.name }}</span>
                      <Check v-if="selectedTag === tag.name" :size="15" class="ml-auto shrink-0 text-accent" aria-hidden="true" />
                      <span v-else-if="tag.count" class="ml-auto shrink-0 text-caption text-subtle tabular-nums">{{ tag.count }}</span>
                    </button>
                    <p v-if="filteredTags.length === 0" class="py-3 text-center text-meta text-subtle">无匹配标签</p>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <p v-if="compact" class="mb-2 text-meta font-medium text-muted">来源</p>
              <UiSegmented v-model="sourceFilter" label="来源筛选" :options="sourceOptions" :block="compact" />
            </div>

            <div v-if="compact">
              <p class="mb-2 text-meta font-medium text-muted">排序</p>
              <UiSegmented v-model="sortBy" label="排序方式" :options="sortOptions" block />
            </div>
            <div v-else ref="sortDropdownRef" class="relative" @keydown.esc.prevent.stop="sortDropdownOpen = false; sortButtonRef?.focus()">
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
              <div v-if="sortDropdownOpen" role="menu" aria-label="排序方式" :class="[popoverClass, 'absolute left-0 top-full z-50 mt-1.5 min-w-44']">
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
            </div>

            <div v-if="compact">
              <p class="mb-2 text-meta font-medium text-muted">显示方式</p>
              <UiSegmented v-model="viewModeModel" label="媒体显示视图" :options="viewSegments" block />
            </div>

            <UiButton v-if="activeFilterCount > 0 && !compact" variant="ghost" size="sm" @click="clearFilters">
              <template #icon><X :size="14" /></template>
              清除筛选
            </UiButton>

            <div v-if="compact" class="flex gap-2 pt-1">
              <UiButton v-if="activeFilterCount > 0" variant="secondary" size="lg" @click="clearFilters">清除</UiButton>
              <UiButton variant="primary" size="lg" block class="flex-1" @click="filtersExpanded = false">查看 {{ totalItems.toLocaleString() }} 项媒体</UiButton>
            </div>
          </div>
        </Teleport>

        <UiSegmented v-if="!compact" v-model="viewModeModel" label="媒体显示视图" :options="viewSegments" class="ml-auto" />
      </div>

      <nav v-if="compact" aria-label="媒体分类" class="he-media-categories -mx-4 mt-3 overflow-x-auto px-4 scrollbar-none">
        <div class="flex w-max gap-2">
          <router-link
            v-for="category in mobileCategories"
            :key="category.path"
            :to="{ path: category.path, query: { ...route.query, page: undefined, media: undefined } }"
            :aria-current="route.path === category.path ? 'page' : undefined"
            class="inline-flex h-10 shrink-0 items-center rounded-full border px-4 text-meta font-medium transition-colors duration-150 focus-ring"
            :class="route.path === category.path ? 'border-accent/50 bg-accent/15 text-accent-glow' : 'border-line bg-surface text-muted'"
          >{{ category.label }}</router-link>
        </div>
      </nav>
    </PageHeader>

    <section v-if="featuredContinue && !searchQuery && !selectedTag" class="page-gutter mt-6" aria-label="今晚继续">
      <div class="page-container">
        <div class="grid overflow-hidden rounded-3xl border border-line bg-surface sm:grid-cols-[240px_1fr]">
          <button type="button" class="group relative min-h-44 overflow-hidden bg-surface-2 text-left focus-ring sm:min-h-full" :aria-label="`打开媒体：${featuredContinue.title}`" @click="openMedia(featuredContinue)">
            <img :src="featuredContinue.cover_path ? thumbnailUrl(featuredContinue.cover_path) : mediaPlaceholderUrl" :alt="featuredContinue.title" class="absolute inset-0 h-full w-full object-cover transition-transform duration-300 group-hover:scale-105" />
            <span class="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent"></span>
            <span class="absolute bottom-3 left-3 inline-flex items-center gap-1.5 rounded-full bg-black/70 px-3 py-1.5 text-caption font-medium text-white"><Play :size="13" fill="currentColor" aria-hidden="true" />继续</span>
          </button>
          <div class="flex min-w-0 flex-col justify-center gap-3 p-5 sm:p-6">
            <p class="text-caption font-medium uppercase tracking-wider text-accent-glow">今晚继续 · {{ continueTitle }}</p>
            <h2 class="line-clamp-2 text-title font-semibold leading-tight text-ink">{{ featuredContinue.title }}</h2>
            <p class="flex flex-wrap items-center gap-x-2 gap-y-1 text-meta text-subtle tabular-nums">
              <span>{{ typeLabel(featuredContinue.media_type) }}</span>
              <span v-if="continueMeta(featuredContinue)" aria-hidden="true">·</span>
              <span v-if="continueMeta(featuredContinue)">{{ continueMeta(featuredContinue) }}</span>
              <span v-if="featuredContinue.rating" aria-hidden="true">·</span>
              <span v-if="featuredContinue.rating">★ {{ featuredContinue.rating }}</span>
              <span v-if="featuredContinue.tags?.length" aria-hidden="true">·</span>
              <span v-if="featuredContinue.tags?.length" class="truncate">{{ featuredContinue.tags.slice(0, 3).map(tag => tag.name).join(' / ') }}</span>
            </p>
            <div v-if="progressPercent(featuredContinue) > 0" class="h-1.5 w-full max-w-md overflow-hidden rounded-full bg-surface-3" role="progressbar" :aria-label="`${featuredContinue.title}观看进度`" :aria-valuenow="progressPercent(featuredContinue)" aria-valuemin="0" aria-valuemax="100">
              <div class="h-full rounded-full bg-accent" :style="{ width: `${progressPercent(featuredContinue)}%` }"></div>
            </div>
            <div class="flex flex-wrap gap-2 pt-1">
              <UiButton variant="primary" @click="openMedia(featuredContinue)"><template #icon><Play :size="15" fill="currentColor" aria-hidden="true" /></template>继续{{ featuredContinue.media_type === 'manga' ? '阅读' : featuredContinue.media_type === 'audio' ? '收听' : '观看' }}</UiButton>
              <UiButton v-if="recentlyOpened.length > 1" variant="secondary" @click="showOtherContinueItems">看看其他继续项</UiButton>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="recentlyOpened.length > 0 && !searchQuery && !selectedTag" ref="continueSectionRef" class="page-gutter mt-6 select-none" aria-label="继续观看">
      <div class="page-container">
        <SectionHeader :title="continueTitle">
          <template #actions>
            <UiButton variant="ghost" size="sm" :title="continueCollapsed ? '展开继续观看' : '收起继续观看'" :aria-expanded="!continueCollapsed" @click="continueCollapsed = !continueCollapsed">
              {{ continueCollapsed ? '展开' : '收起' }}
              <template #trailing><ChevronDown :size="14" class="transition-transform duration-150" :class="{ '-rotate-90': continueCollapsed }" aria-hidden="true" /></template>
            </UiButton>
            <template v-if="!continueCollapsed && !compact">
              <UiIconButton label="向左滚动" variant="secondary" size="sm" @click="scrollContinue(-1)"><ChevronLeft :size="16" aria-hidden="true" /></UiIconButton>
              <UiIconButton label="向右滚动" variant="secondary" size="sm" @click="scrollContinue(1)"><ChevronRight :size="16" aria-hidden="true" /></UiIconButton>
            </template>
          </template>
        </SectionHeader>
        <Transition name="he-continue-reveal">
        <div v-show="!continueCollapsed" ref="continueScrollRef" :inert="continueCollapsed" class="-mx-4 flex gap-3 overflow-x-auto px-4 pb-1 scrollbar-none sm:-mx-6 sm:px-6 lg:mx-0 lg:px-0" :class="continueDragging ? 'cursor-grabbing' : 'cursor-grab'" @pointerdown="startContinueDrag" @pointermove="moveContinueDrag" @pointerup="endContinueDrag" @pointercancel="endContinueDrag" @lostpointercapture="endContinueDrag" @click.capture="preventDraggedClick" @dragstart.prevent>
          <div
            v-for="item in recentlyOpened"
            :key="item.id"
            class="group relative flex w-72 shrink-0 items-center gap-3 rounded-2xl border border-line bg-surface p-2.5 transition-colors duration-150 ease-out hover:border-line-strong hover:bg-surface-2"
          >
            <button
              type="button"
              class="absolute inset-0 z-10 rounded-2xl focus-ring"
              :aria-label="`打开媒体：${item.title}`"
              @click="openMedia(item)"
            ></button>
            <div class="relative h-16 shrink-0 overflow-hidden rounded-lg bg-surface-2" :class="continueThumbClass(item)">
              <img :src="item.cover_path ? thumbnailUrl(item.cover_path) : mediaPlaceholderUrl" alt="" class="h-full w-full object-cover" />
              <div class="pointer-events-none absolute inset-0 rounded-lg ring-1 ring-inset ring-white/8"></div>
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
        </Transition>
      </div>
    </section>

    <div ref="containerRef" class="page-gutter pb-12" :class="recentlyOpened.length > 0 && !searchQuery && !selectedTag ? 'mt-8' : 'mt-6'">
      <div class="page-container">
        <div v-if="loading" data-media-grid :class="viewMode === 'list' ? 'flex flex-col gap-2' : viewMode === 'wide' ? 'grid grid-cols-1 gap-x-5 gap-y-7 md:grid-cols-2 xl:grid-cols-3' : viewMode === 'poster' ? posterGridClass : 'poster-grid'">
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

        <div v-else-if="mediaList.length > 0" class="flex flex-col gap-10">
          <div v-if="viewMode === 'poster'" data-media-grid :class="posterGridClass">
            <div v-for="(item, index) in mediaList" :key="item.id" class="he-media-actions relative min-w-0">
              <MediaCard :media="item" :index="index" :shape="cardShape" :show-type="!mediaType" @click="openMedia(item)" />
              <button v-if="authState.user?.is_admin" type="button" class="he-media-delete absolute right-2 top-2 z-10 grid size-11 place-items-center rounded-xl bg-black/75 text-white/85 transition-colors hover:bg-danger hover:text-white focus-ring" :aria-label="`删除并丢弃 ${item.title}`" title="删除并丢弃" @click.stop="discardTarget = { kind: 'media', target_id: item.id }"><Trash2 :size="17" aria-hidden="true" /></button>
            </div>
          </div>
          <div v-else data-media-grid :class="viewMode === 'masonry' ? 'masonry-grid' : viewMode === 'wide' ? 'grid grid-cols-1 gap-x-5 gap-y-7 md:grid-cols-2 xl:grid-cols-3' : 'flex flex-col gap-2'">
            <div v-for="item in mediaList" :key="item.id" class="he-media-actions relative min-w-0" :class="viewMode === 'masonry' ? 'masonry-grid-item' : viewMode === 'list' ? 'flex items-center gap-2' : ''">
              <MediaViewCard :media="item" :mode="viewMode" :class="viewMode === 'list' ? 'min-w-0 flex-1' : ''" @click="openMedia(item)" />
              <button v-if="authState.user?.is_admin" type="button" class="he-media-delete grid size-11 shrink-0 place-items-center rounded-xl transition-colors hover:bg-danger hover:text-white focus-ring" :class="viewMode === 'list' ? 'bg-surface text-subtle' : 'absolute right-2 top-2 z-10 bg-black/75 text-white/85'" :aria-label="`删除并丢弃 ${item.title}`" title="删除并丢弃" @click.stop="discardTarget = { kind: 'media', target_id: item.id }"><Trash2 :size="17" aria-hidden="true" /></button>
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
.he-continue-reveal-enter-active, .he-continue-reveal-leave-active {
  overflow-y: hidden;
  transition: max-height 220ms ease, opacity 180ms ease;
}
.he-continue-reveal-enter-from, .he-continue-reveal-leave-to { max-height: 0; opacity: 0; }
.he-continue-reveal-enter-to, .he-continue-reveal-leave-from { max-height: 160px; opacity: 1; }
@media (prefers-reduced-motion: reduce) {
  .he-continue-reveal-enter-active, .he-continue-reveal-leave-active { transition: none; }
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
