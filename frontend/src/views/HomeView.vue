<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { Book, ChevronDown, ChevronLeft, ChevronRight, Filter, History, Play, Search, SortAsc, Star, X } from 'lucide-vue-next'
import { API_BASE_URL, thumbnailUrl } from '../config'
import { authState } from '../auth'
import type { Media, Tag } from '../types'
import MediaCard from '../components/MediaCard.vue'
import MediaDetail from '../components/MediaDetail.vue'

const props = defineProps<{
  mediaType?: string
}>()

const route = useRoute()
const router = useRouter()
const mediaList = ref<Media[]>([])
const tags = ref<Tag[]>([])
const loading = ref(true)
const mediaError = ref('')
const selectedMedia = ref<Media | null>(null)
const searchQuery = ref('')
const sortBy = ref<'date' | 'title' | 'rating' | 'opened'>('date')
const selectedTag = ref('')
const tagDropdownOpen = ref(false)
const favoriteOnly = ref(false)
const sourceFilter = ref<'' | 'x' | 'wnacg' | 'local'>('')
const filtersExpanded = ref(false)
const continueScrollRef = ref<HTMLElement | null>(null)

const activeFilterCount = computed(() => {
  return Number(Boolean(selectedTag.value)) + Number(Boolean(sourceFilter.value)) + Number(sortBy.value !== 'date')
})

const clearFilters = () => {
  selectedTag.value = ''
  sourceFilter.value = ''
  sortBy.value = 'date'
}

const scrollContinue = (direction: -1 | 1) => {
  const el = continueScrollRef.value
  if (!el) return
  el.scrollBy({ left: direction * Math.max(220, el.clientWidth * 0.72), behavior: 'smooth' })
}

const progressPercent = (media: Media) => {
  if (media.media_type === 'video' && media.duration && media.progress > 0) {
    return Math.min(100, Math.max(0, Math.round((media.progress / media.duration) * 100)))
  }
  if (media.media_type === 'manga' && media.page_count && media.progress >= 0) {
    return Math.min(100, Math.max(0, Math.round(((media.progress + 1) / media.page_count) * 100)))
  }
  return 0
}

const recentlyOpened = computed(() => {
  return [...mediaList.value]
    .filter(item => item.last_opened_at || progressPercent(item) > 0)
    .sort((a, b) => {
      const timeA = a.last_opened_at ? new Date(a.last_opened_at).getTime() : 0
      const timeB = b.last_opened_at ? new Date(b.last_opened_at).getTime() : 0
      return timeB - timeA
    })
    .slice(0, 8)
})

const limit = 80
const offset = ref(0)
const hasMore = ref(true)
const loadingMore = ref(false)
const loadMoreRef = ref<HTMLElement | null>(null)
const containerRef = ref<HTMLElement | null>(null)
const virtualGridRef = ref<HTMLElement | null>(null)
const virtualItemsRef = ref<HTMLElement | null>(null)
const virtualColumns = ref(2)
const virtualRowHeight = ref(360)
const virtualRowGap = ref(20)
const virtualStartRow = ref(0)
const virtualEndRow = ref(8)
const virtualOverscan = 6
let observer: IntersectionObserver | null = null
let scrollRoot: HTMLElement | null = null
let resizeObserver: ResizeObserver | null = null
let virtualFrame = 0
let hasCompletedInitialFetch = false
let lastVirtualScrollTop = 0
let virtualScrollDirection: -1 | 0 | 1 = 0
let lastVirtualGridWidth = 0

const virtualRowCount = computed(() => Math.ceil(mediaList.value.length / virtualColumns.value))
const virtualStartIndex = computed(() => virtualStartRow.value * virtualColumns.value)
const virtualEndIndex = computed(() => Math.min(
  mediaList.value.length,
  virtualEndRow.value * virtualColumns.value,
))
const virtualMedia = computed(() => mediaList.value.slice(virtualStartIndex.value, virtualEndIndex.value))
const virtualOffsetY = computed(() => virtualStartRow.value * (virtualRowHeight.value + virtualRowGap.value))
const virtualTotalHeight = computed(() => {
  if (virtualRowCount.value === 0) return 0
  return virtualRowCount.value * virtualRowHeight.value
    + (virtualRowCount.value - 1) * virtualRowGap.value
})

const fallbackColumnCount = () => {
  if (window.innerWidth >= 1536) return 6
  if (window.innerWidth >= 1280) return 5
  if (window.innerWidth >= 1024) return 4
  if (window.innerWidth >= 640) return 3
  return 2
}

const updateVirtualWindow = () => {
  if (!scrollRoot || !virtualGridRef.value || virtualRowCount.value === 0) {
    virtualStartRow.value = 0
    virtualEndRow.value = Math.min(8, virtualRowCount.value)
    return
  }

  const rootRect = scrollRoot.getBoundingClientRect()
  const gridRect = virtualGridRef.value.getBoundingClientRect()
  const gridTop = gridRect.top - rootRect.top + scrollRoot.scrollTop
  const relativeTop = Math.max(0, scrollRoot.scrollTop - gridTop)
  const stride = Math.max(1, virtualRowHeight.value + virtualRowGap.value)
  const firstVisibleRow = Math.floor(relativeTop / stride)
  const lastVisibleRow = Math.ceil((relativeTop + scrollRoot.clientHeight) / stride)
  const scrollDistance = Math.abs(scrollRoot.scrollTop - lastVirtualScrollTop)
  const directionalBuffer = Math.min(12, Math.ceil(scrollDistance / stride))
  const startBuffer = virtualOverscan + (virtualScrollDirection < 0 ? directionalBuffer : 0)
  const endBuffer = virtualOverscan + (virtualScrollDirection > 0 ? directionalBuffer : 0)
  const nextStartRow = Math.max(0, firstVisibleRow - startBuffer)
  const nextEndRow = Math.min(virtualRowCount.value, lastVisibleRow + endBuffer)

  if (nextStartRow !== virtualStartRow.value) virtualStartRow.value = nextStartRow
  if (nextEndRow !== virtualEndRow.value) virtualEndRow.value = nextEndRow
}

const updateVirtualLayout = async (force = false) => {
  const grid = virtualGridRef.value
  if (!grid) return

  const gridWidth = grid.clientWidth
  if (!force && Math.abs(gridWidth - lastVirtualGridWidth) < 0.5) {
    updateVirtualWindow()
    return
  }

  const items = virtualItemsRef.value
  const computedGrid = items ? window.getComputedStyle(items) : null
  const templateColumns = computedGrid?.gridTemplateColumns || ''
  const measuredColumns = templateColumns && templateColumns !== 'none'
    ? templateColumns.split(' ').filter(Boolean).length
    : 0
  const columns = measuredColumns || fallbackColumnCount()
  const gap = computedGrid ? Number.parseFloat(computedGrid.rowGap) || 20 : (window.innerWidth >= 768 ? 28 : 20)
  const cardWidth = Math.max(1, (gridWidth - gap * (columns - 1)) / columns)

  lastVirtualGridWidth = gridWidth
  virtualColumns.value = columns
  virtualRowGap.value = gap
  virtualRowHeight.value = cardWidth * 1.5 + 42
  updateVirtualWindow()

  await nextTick()
  const card = virtualItemsRef.value?.querySelector<HTMLElement>('.lazy-card')
  const measuredHeight = card?.getBoundingClientRect().height || 0
  if (measuredHeight > 0 && Math.abs(measuredHeight - virtualRowHeight.value) > 0.5) {
    virtualRowHeight.value = measuredHeight
    updateVirtualWindow()
  }
}

const scheduleVirtualUpdate = (remeasure = false) => {
  window.cancelAnimationFrame(virtualFrame)
  virtualFrame = window.requestAnimationFrame(() => {
    if (remeasure) {
      void updateVirtualLayout(true)
    } else {
      updateVirtualWindow()
    }
  })
}

const handleVirtualScroll = () => {
  let nextScrollTop = lastVirtualScrollTop
  if (scrollRoot) {
    nextScrollTop = scrollRoot.scrollTop
    virtualScrollDirection = nextScrollTop === lastVirtualScrollTop
      ? 0
      : nextScrollTop > lastVirtualScrollTop ? 1 : -1
  }
  // Do not wait for requestAnimationFrame: a fast scroll must keep its visible
  // rows mounted in the same frame, otherwise the grid briefly goes blank.
  updateVirtualWindow()
  lastVirtualScrollTop = nextScrollTop
  maybeLoadMore()
}

const scrollListToStart = () => {
  if (!scrollRoot || !containerRef.value) return
  const rootRect = scrollRoot.getBoundingClientRect()
  const containerRect = containerRef.value.getBoundingClientRect()
  const targetTop = scrollRoot.scrollTop + containerRect.top - rootRect.top - 16
  scrollRoot.scrollTo({ top: Math.max(0, targetTop), behavior: 'auto' })
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

const selectTag = (tagName: string) => {
  selectedTag.value = tagName
  tagDropdownOpen.value = false
}

const fetchTags = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/tags`)
    tags.value = res.data
  } catch (err) {
    console.error('Failed to fetch tags:', err)
  }
}

const fetchMedia = async () => {
  if (hasCompletedInitialFetch) scrollListToStart()
  loading.value = true
  mediaError.value = ''
  offset.value = 0
  hasMore.value = true
  try {
    const params: Record<string, string | number | boolean | undefined> = {
      media_type: props.mediaType,
      search: searchQuery.value.trim() || undefined,
      tag: selectedTag.value || undefined,
      favorite: favoriteOnly.value ? true : undefined,
      source_site: sourceFilter.value || undefined,
      sort: sortBy.value,
      limit,
      offset: 0,
    }
    const res = await axios.get(`${API_BASE_URL}/media`, { params })
    mediaList.value = res.data
    if (res.data.length < limit) {
      hasMore.value = false
    }
  } catch (err: any) {
    console.error('Failed to fetch media:', err)
    mediaList.value = []
    hasMore.value = false
    const status = err?.response?.status
    mediaError.value = status === 401
      ? '登录状态已失效，请重新登录。'
      : status === 403
        ? '当前账号没有权限读取媒体列表。'
        : '无法加载媒体列表，请检查后端连接。'
  } finally {
    loading.value = false
    hasCompletedInitialFetch = true
  }
}

const loadMore = async () => {
  if (loading.value || loadingMore.value || !hasMore.value) return
  loadingMore.value = true
  const nextOffset = offset.value + limit
  try {
    const params: Record<string, string | number | boolean | undefined> = {
      media_type: props.mediaType,
      search: searchQuery.value || undefined,
      tag: selectedTag.value || undefined,
      favorite: favoriteOnly.value ? true : undefined,
      source_site: sourceFilter.value || undefined,
      sort: sortBy.value,
      limit,
      offset: nextOffset,
    }
    const res = await axios.get(`${API_BASE_URL}/media`, { params })
    mediaList.value.push(...res.data)
    offset.value = nextOffset
    if (res.data.length < limit) {
      hasMore.value = false
    }
  } catch (err) {
    console.error('Failed to load more media:', err)
  } finally {
    loadingMore.value = false
    await nextTick()
    maybeLoadMore()
  }
}

const observeLoadMore = () => {
  if (observer) observer.disconnect()
  const el = loadMoreRef.value
  if (el) {
    observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore.value && !loading.value && !loadingMore.value) {
        void loadMore()
      }
    }, { root: scrollRoot, rootMargin: '0px 0px 1600px 0px' })
    observer.observe(el)
  }
}

function maybeLoadMore() {
  if (!scrollRoot || loading.value || loadingMore.value || !hasMore.value) return
  const remaining = scrollRoot.scrollHeight - scrollRoot.scrollTop - scrollRoot.clientHeight
  if (remaining < Math.max(1000, scrollRoot.clientHeight * 2)) {
    void loadMore()
  }
}

watch(loadMoreRef, () => {
  observeLoadMore()
})

watch(() => mediaList.value.length, () => {
  scheduleVirtualUpdate(false)
}, { flush: 'post' })

onUnmounted(() => {
  observer?.disconnect()
  resizeObserver?.disconnect()
  scrollRoot?.removeEventListener('scroll', handleVirtualScroll)
  window.cancelAnimationFrame(virtualFrame)
})

const updateMediaInList = (media: Media) => {
  const index = mediaList.value.findIndex(item => item.id === media.id)
  if (index >= 0) {
    mediaList.value[index] = media
  }
  if (selectedMedia.value?.id === media.id) {
    selectedMedia.value = media
  }
  fetchTags()
}

const openMedia = (media: Media, replace = false) => {
  selectedMedia.value = media
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
  selectedMedia.value = null
  const query = { ...route.query }
  delete query.media
  router.push({ path: route.path, query })
}

const syncSelectedMediaFromRoute = async () => {
  const mediaId = Number(route.query.media)
  if (!mediaId) {
    selectedMedia.value = null
    return
  }

  if (selectedMedia.value?.id === mediaId) return

  const localMedia = mediaList.value.find(item => item.id === mediaId)
  if (localMedia) {
    selectedMedia.value = localMedia
    return
  }

  try {
    const res = await axios.get(`${API_BASE_URL}/media/${mediaId}`)
    selectedMedia.value = res.data
  } catch (err) {
    console.error('Failed to fetch selected media:', err)
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
watch(searchQuery, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(fetchMedia, 250)
})

watch([() => props.mediaType, selectedTag, sortBy, favoriteOnly, sourceFilter], fetchMedia)
watch(() => route.query.favorite, value => {
  favoriteOnly.value = value === 'true'
}, { immediate: true })
watch(() => route.query.source, value => {
  const v = typeof value === 'string' ? value : ''
  sourceFilter.value = (v === 'x' || v === 'wnacg' || v === 'local') ? v : ''
}, { immediate: true })
watch(() => route.query.media, () => {
  syncSelectedMediaFromRoute()
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
  await fetchMedia()
  await nextTick()
  scrollRoot = containerRef.value?.closest<HTMLElement>('.main-scroll-container') || null
  lastVirtualScrollTop = scrollRoot?.scrollTop || 0
  scrollRoot?.addEventListener('scroll', handleVirtualScroll, { passive: true })
  resizeObserver = new ResizeObserver(() => scheduleVirtualUpdate(true))
  if (containerRef.value) resizeObserver.observe(containerRef.value)
  await updateVirtualLayout()
  observeLoadMore()
  maybeLoadMore()
  await syncSelectedMediaFromRoute()
  fetchTags()
  await triggerMissingRecheck()
})
</script>

<template>
  <div class="z-10 relative">
    <header class="sticky top-0 z-40 bg-background/55 backdrop-blur-2xl border-b border-white/5 px-6 md:px-8 py-4 mb-6 shadow-[0_4px_30px_rgba(0,0,0,0.4)]">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-baseline gap-3">
          <h1 class="text-xl md:text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-white via-white to-white/60 tracking-tight">
            {{ pageTitle }}
          </h1>
          <span class="text-[9px] font-black text-accent bg-accent/10 px-2 py-0.5 rounded-md border border-accent/20 uppercase tracking-widest">
            {{ mediaList.length.toLocaleString() }} 项
          </span>
        </div>

        <div class="flex flex-1 min-w-[260px] max-w-3xl gap-3">
          <div class="relative flex-1 group">
            <Search class="absolute left-4 top-1/2 -translate-y-1/2 text-white/25 group-focus-within:text-accent transition-colors duration-300" :size="16" />
            <input
              v-model="searchQuery"
              type="text"
              placeholder="搜索标题、文件名..."
              class="w-full bg-white/4 border border-white/5 rounded-xl pl-11 pr-4 py-2.5 text-xs text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-accent/25 focus:bg-white/6 focus:border-white/12 shadow-[inset_0_1px_2px_rgba(0,0,0,0.3)] transition-all duration-300"
            />
          </div>

          <button
            @click="toggleFavoriteFilter"
            :class="favoriteOnly ? 'bg-gradient-to-tr from-accent to-indigo-500 text-white shadow-md shadow-accent/15 border border-accent/20 scale-102' : 'bg-white/4 border border-white/5 text-white/50 hover:bg-white/6 hover:text-white hover:border-white/10 hover:shadow-md'"
            class="w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-300 cursor-pointer"
            title="只看收藏"
          >
            <Star :size="16" :fill="favoriteOnly ? 'currentColor' : 'none'" />
          </button>

          <button
            @click="filtersExpanded = !filtersExpanded"
            :class="filtersExpanded || activeFilterCount > 0 ? 'bg-accent/15 border-accent/30 text-accent' : 'bg-white/4 border-white/5 text-white/55 hover:text-white'"
            class="md:hidden relative w-10 h-10 rounded-xl border flex items-center justify-center transition-all"
            :aria-expanded="filtersExpanded"
            title="展开筛选"
          >
            <Filter :size="16" />
            <span v-if="activeFilterCount" class="absolute -right-1 -top-1 min-w-4 h-4 px-1 rounded-full bg-accent text-[9px] font-black text-white flex items-center justify-center">
              {{ activeFilterCount }}
            </span>
          </button>
        </div>
      </div>

      <div
        :class="filtersExpanded ? 'flex' : 'hidden md:flex'"
        class="mt-3.5 flex-wrap items-center gap-3 text-xs rounded-2xl md:rounded-none bg-white/[0.025] md:bg-transparent border border-white/5 md:border-0 p-3 md:p-0"
      >
        <div class="flex items-center gap-1.5 text-white/35 font-bold">
          <Filter :size="13" />
          <span class="text-[10px] uppercase tracking-wider">筛选</span>
        </div>

        <!-- Tag Dropdown -->
        <div class="relative">
          <button
            @click="tagDropdownOpen = !tagDropdownOpen"
            class="min-w-32 bg-white/4 border border-white/5 rounded-xl px-3 py-2 text-[11px] text-white/70 focus:outline-none focus:ring-2 focus:ring-accent/20 flex items-center justify-between gap-3 hover:bg-white/6 hover:border-white/10 transition-all duration-300 cursor-pointer font-bold"
          >
            <span class="truncate">{{ selectedTagLabel }}</span>
            <ChevronDown :size="12" :class="tagDropdownOpen ? 'rotate-180' : ''" class="transition-transform text-white/35" />
          </button>
          <div
            v-if="tagDropdownOpen"
            class="absolute left-0 top-full mt-1.5 z-50 min-w-44 max-h-64 overflow-y-auto rounded-2xl border border-white/8 bg-sidebar/70 backdrop-blur-3xl shadow-2xl p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] custom-scrollbar"
          >
            <button
              @click="selectTag('')"
              :class="selectedTag === '' ? 'bg-accent text-white shadow-sm shadow-accent/15' : 'text-white/70 hover:text-white hover:bg-white/6'"
              class="w-full rounded-xl px-3 py-2 text-left text-[11px] font-bold transition-all duration-200 cursor-pointer"
            >
              全部标签
            </button>
            <button
              v-for="tag in tags"
              :key="tag.id"
              @click="selectTag(tag.name)"
              :class="selectedTag === tag.name ? 'bg-accent text-white shadow-sm shadow-accent/15' : 'text-white/70 hover:text-white hover:bg-white/6'"
              class="w-full rounded-xl px-3 py-2 text-left text-[11px] font-bold transition-all duration-200 cursor-pointer"
            >
              {{ tag.name }}
            </button>
          </div>
        </div>

        <!-- Source Filter (Slide segmented Pill) -->
        <div class="flex bg-white/3 rounded-xl p-0.5 border border-white/5 shadow-inner">
          <button
            @click="sourceFilter = ''"
            :class="sourceFilter === '' ? 'bg-accent text-white shadow-sm shadow-accent/10' : 'text-white/50 hover:text-white hover:bg-white/3'"
            class="px-2.5 py-1.5 rounded-lg text-[10px] font-bold transition-all duration-250 cursor-pointer"
          >
            全部
          </button>
          <button
            @click="sourceFilter = 'local'"
            :class="sourceFilter === 'local' ? 'bg-accent text-white shadow-sm shadow-accent/10' : 'text-white/50 hover:text-white hover:bg-white/3'"
            class="px-2.5 py-1.5 rounded-lg text-[10px] font-bold transition-all duration-250 cursor-pointer"
            title="本地扫描的媒体"
          >
            本地
          </button>
          <button
            @click="sourceFilter = 'x'"
            :class="sourceFilter === 'x' ? 'bg-accent text-white shadow-sm shadow-accent/10' : 'text-white/50 hover:text-white hover:bg-white/3'"
            class="px-2.5 py-1.5 rounded-lg text-[10px] font-bold transition-all duration-250 cursor-pointer"
            title="X (Twitter) 导入"
          >
            X
          </button>
          <button
            @click="sourceFilter = 'wnacg'"
            :class="sourceFilter === 'wnacg' ? 'bg-accent text-white shadow-sm shadow-accent/10' : 'text-white/50 hover:text-white hover:bg-white/3'"
            class="px-2.5 py-1.5 rounded-lg text-[10px] font-bold transition-all duration-250 cursor-pointer"
            title="wnacg 下载"
          >
            wnacg
          </button>
        </div>

        <!-- Sort Filter -->
        <div class="flex bg-white/3 rounded-xl p-0.5 border border-white/5 shadow-inner">
          <button
            @click="sortBy = 'date'"
            :class="sortBy === 'date' ? 'bg-accent text-white shadow-sm shadow-accent/10' : 'text-white/50 hover:text-white hover:bg-white/3'"
            class="px-2.5 py-1.5 rounded-lg text-[10px] font-bold transition-all duration-250 cursor-pointer"
          >
            最近添加
          </button>
          <button
            @click="sortBy = 'opened'"
            :class="sortBy === 'opened' ? 'bg-accent text-white shadow-sm shadow-accent/10' : 'text-white/50 hover:text-white hover:bg-white/3'"
            class="px-2.5 py-1.5 rounded-lg text-[10px] font-bold transition-all duration-250 cursor-pointer"
          >
            最近打开
          </button>
          <button
            @click="sortBy = 'rating'"
            :class="sortBy === 'rating' ? 'bg-accent text-white shadow-sm shadow-accent/10' : 'text-white/50 hover:text-white hover:bg-white/3'"
            class="px-2.5 py-1.5 rounded-lg text-[10px] font-bold transition-all duration-250 cursor-pointer"
          >
            评分
          </button>
          <button
            @click="sortBy = 'title'"
            :class="sortBy === 'title' ? 'bg-accent text-white shadow-sm shadow-accent/10' : 'text-white/50 hover:text-white hover:bg-white/3'"
            class="px-2.5 py-1.5 rounded-lg text-[10px] font-bold transition-all duration-250 flex items-center gap-1 cursor-pointer"
          >
            <SortAsc :size="11" /> 名称
          </button>
        </div>

        <button
          v-if="activeFilterCount > 0"
          @click="clearFilters"
          class="h-8 px-3 rounded-xl border border-white/8 bg-white/3 text-[10px] font-bold text-white/55 hover:text-white hover:bg-white/8 flex items-center gap-1.5 transition-all"
        >
          <X :size="12" />
          清除筛选
        </button>
      </div>
    </header>

    <!-- Continue watch/read section -->
    <div v-if="recentlyOpened.length > 0 && !searchQuery && !selectedTag" class="px-6 md:px-8 mb-8 animate-fluid-entrance select-none">
      <div class="flex items-center justify-between gap-3 mb-3.5">
        <div class="flex items-center gap-2">
          <History class="text-accent" :size="15" />
          <h2 class="text-[10px] font-black text-white/50 tracking-widest uppercase">继续观看 / 阅读</h2>
        </div>
        <div class="flex items-center gap-1">
          <button @click="scrollContinue(-1)" class="w-8 h-8 rounded-lg border border-white/8 bg-white/4 text-white/55 hover:text-white hover:bg-white/8 flex items-center justify-center transition-all" title="向左滚动">
            <ChevronLeft :size="16" />
          </button>
          <button @click="scrollContinue(1)" class="w-8 h-8 rounded-lg border border-white/8 bg-white/4 text-white/55 hover:text-white hover:bg-white/8 flex items-center justify-center transition-all" title="向右滚动">
            <ChevronRight :size="16" />
          </button>
        </div>
      </div>
      <div class="relative -mx-1 px-1">
        <div class="pointer-events-none absolute right-0 top-0 bottom-2 w-12 bg-gradient-to-l from-background to-transparent z-10"></div>
        <div ref="continueScrollRef" class="flex gap-4 overflow-x-auto pb-2 pr-10 custom-scrollbar scroll-smooth">
        <div
          v-for="item in recentlyOpened"
          :key="item.id"
          class="shrink-0 w-52 sm:w-60 bg-gradient-to-b from-white/5 to-white/[0.01] rounded-xl border border-white/5 p-2.5 hover:border-white/15 transition-all duration-300 cursor-pointer flex gap-3 relative shadow-md hover:shadow-[0_12px_24px_-10px_rgba(var(--color-accent),0.15)] group"
          @click="openMedia(item)"
        >
          <div class="w-14 h-18 shrink-0 rounded-lg overflow-hidden bg-black/40 border border-white/5 relative">
            <img :src="item.cover_path ? thumbnailUrl(item.cover_path) : 'https://via.placeholder.com/100x150'" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
            <div class="absolute inset-0 bg-black/30 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
              <Play v-if="item.media_type === 'video'" :size="12" fill="white" class="text-white" />
              <Book v-else :size="12" class="text-white" />
            </div>
          </div>
          <div class="flex-1 min-w-0 flex flex-col justify-between py-0.5">
            <div>
              <h3 class="text-xs font-bold text-white/85 group-hover:text-accent truncate transition-colors leading-tight mb-1" :title="item.title">{{ item.title }}</h3>
              <p class="text-[9px] font-bold text-white/35 uppercase tracking-wider">
                {{ item.media_type === 'manga' ? '漫画' : item.media_type === 'video' ? '视频' : item.media_type === 'audio' ? '音频' : '杂图' }}
              </p>
            </div>
            <div v-if="progressPercent(item) > 0" class="space-y-1">
              <div class="flex items-center justify-between text-[8px] font-bold text-white/40">
                <span>已看 {{ progressPercent(item) }}%</span>
              </div>
              <div class="h-1 w-full bg-white/10 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-300"
                  :class="item.media_type === 'manga' ? 'bg-purple-400' : 'bg-accent'"
                  :style="{ width: `${progressPercent(item)}%` }"
                ></div>
              </div>
            </div>
          </div>
        </div>
        </div>
      </div>
    </div>

    <div ref="containerRef" class="px-6 md:px-8 pb-12">
      <div v-if="loading" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-5 md:gap-7">
        <div v-for="i in 12" :key="i" class="aspect-[3/4.5] bg-white/5 animate-pulse rounded-2xl border border-white/5"></div>
      </div>

      <div v-else-if="mediaError" class="flex flex-col items-center justify-center py-32 text-amber-100 text-center">
        <div class="w-16 h-16 rounded-2xl bg-amber-400/10 flex items-center justify-center mb-5 border border-amber-300/20">
          <Search :size="28" />
        </div>
        <p class="text-lg font-bold mb-2">媒体列表加载失败</p>
        <p class="text-sm text-amber-100/75">{{ mediaError }}</p>
      </div>

      <div
        v-else-if="mediaList.length > 0"
        class="flex flex-col gap-8"
      >
        <div
          ref="virtualGridRef"
          class="relative w-full"
          :style="{ height: `${virtualTotalHeight}px` }"
          :data-virtual-total="mediaList.length"
          :data-virtual-start="virtualStartIndex"
          :data-virtual-end="virtualEndIndex"
          style="contain: layout paint style"
        >
          <div
            ref="virtualItemsRef"
            class="virtual-media-grid absolute inset-x-0 top-0 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-5 md:gap-7"
            :style="{ transform: `translate3d(0, ${virtualOffsetY}px, 0)` }"
          >
            <MediaCard
              v-for="(item, visibleIndex) in virtualMedia"
              :key="item.id"
              :media="item"
              :index="virtualStartIndex + visibleIndex"
              virtualized
              eager
              @click="openMedia(item)"
            />
          </div>
        </div>

        <div ref="loadMoreRef" class="w-full py-4 flex justify-center">
          <div v-if="loadingMore" class="text-white/45 flex items-center gap-2">
            <div class="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin"></div>
            <span>加载中...</span>
          </div>
          <button
            v-else-if="hasMore"
            @click="loadMore"
            class="px-6 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl text-sm font-bold text-white transition-all"
          >
            加载更多
          </button>
        </div>
      </div>

      <div v-else-if="!loading && mediaList.length === 0" class="flex flex-col items-center justify-center py-32 text-white/35 text-center">
        <div class="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-5 border border-white/10">
          <Search :size="28" />
        </div>
        <p class="text-lg font-bold mb-2">没有找到匹配的媒体</p>
        <p class="text-sm">可以去设置页添加扫描目录，或调整当前筛选条件。</p>
      </div>
    </div>

    <MediaDetail
      v-if="selectedMedia"
      :initial-media="selectedMedia"
      :all-media="mediaList"
      @close="closeMedia"
      @updated="updateMediaInList"
      @navigate="openMedia($event, true)"
    />
  </div>
</template>
