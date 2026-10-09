<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Columns2,
  GalleryHorizontal,
  Keyboard,
  RotateCcw,
  ScrollText,
  Square,
  ZoomIn,
  ZoomOut,
  X,
} from 'lucide-vue-next'
import { API_BASE_URL, authUrl } from '../../config'
import type { Media } from '../../types'
import { useImageViewerZoom } from '../../composables/useImageViewerZoom'
import { useReaderImageBuffer } from '../../composables/useReaderImageBuffer'

export type MangaReadMode = 'single' | 'double' | 'webtoon'

const props = defineProps<{
  media: Media
  imagePages?: Media[]
  hasNextBatch?: boolean
  hasPreviousBatch?: boolean
  currentPage: number
  totalPages: number | null
  pageDimensions: Array<[number, number] | null>
  showControls: boolean
  clickOnlyControls: boolean
  progressText: string
  progressPercent: number
}>()

const emit = defineEmits<{
  'update:currentPage': [page: number]
  viewerClick: []
  viewerDoubleClick: []
  controlsHover: [hovering: boolean]
  boundary: [direction: -1 | 1]
  loadMore: []
}>()

const mobileReader = window.innerWidth < 900
const preferencePrefix = props.imagePages ? 'he_image' : 'he_manga'
const modeKey = `${preferencePrefix}_read_mode${mobileReader ? '_mobile' : ''}`
const savedMode = localStorage.getItem(modeKey)
const readMode = ref<MangaReadMode>(savedMode === 'single' || savedMode === 'double' || savedMode === 'webtoon' ? savedMode : mobileReader ? 'webtoon' : 'single')
const isRtl = ref(localStorage.getItem(`${preferencePrefix}_rtl`) === 'true')
const showShortcutGuide = ref(false)

const stripKey = mobileReader ? 'he_manga_strip_collapsed_mobile' : 'he_manga_strip_collapsed'
const isStripCollapsed = ref(localStorage.getItem(stripKey) === 'true' || (mobileReader && localStorage.getItem(stripKey) === null))
const toggleStripCollapsed = () => {
  isStripCollapsed.value = !isStripCollapsed.value
  localStorage.setItem(stripKey, String(isStripCollapsed.value))
}
const isStripOpen = computed(() => !props.imagePages && (props.showControls || !props.clickOnlyControls) && !isStripCollapsed.value)

const thumbStripRef = ref<HTMLDivElement | null>(null)
const imageContainerRef = ref<HTMLDivElement | null>(null)
const webtoonContainerRef = ref<HTMLDivElement | null>(null)
const thumbStripScroll = ref(0)
const stripContainerWidth = ref(800)
let stripResizeObserver: ResizeObserver | null = null
const hoverThumbIndex = ref(-1)
const hoverThumbX = ref(0)
const hoverThumbY = ref(0)
let hoverTimer: number | undefined
let isDragging = false
let dragStartX = 0
let dragScrollStart = 0
let dragMoved = false
let lastWheelAt = 0
let isProgrammaticScroll = false
let programmaticScrollTimer: number | undefined
let scrollReportedPage: number | null = null
let webtoonScrollRafId: number | null = null
let scrollRafId: number | null = null
let dragRafId: number | null = null
let pendingDragScroll = 0

const {
  scale: zoomScale,
  translateX: zoomTx,
  translateY: zoomTy,
  isZoomed,
  isPanning: isZoomPanning,
  zoomPercent,
  zoomIn,
  zoomOut,
  resetZoom,
  handleZoomWheel,
  onMouseDown: onZoomMouseDown,
  wasDragging: wasZoomDragging,
  onTouchStart, onTouchMove, onTouchEnd, wasTouchGesture,
} = useImageViewerZoom(imageContainerRef, { onSwipe: direction => { if ((direction === 1) !== isRtl.value) nextPage(); else previousPage() } })

const THUMB_W = 110
const THUMB_H = 148
const THUMB_GAP = 12
const THUMB_PAD = 24
const THUMB_BUFFER = 8
const WHEEL_INTERVAL_MS = 320

const stepSize = computed(() => (readMode.value === 'double' ? 2 : 1))

const pageUrlFor = (page: number) => props.imagePages
  ? authUrl(`${API_BASE_URL}/stream/${props.imagePages[page]?.id}`)
  : authUrl(`${API_BASE_URL}/manga/${props.media.id}/page/${page}`)
const pageUrl = computed(() => pageUrlFor(props.currentPage))
const secondPageUrl = computed(() => {
  if (readMode.value !== 'double') return null
  const nextP = props.currentPage + 1
  if (props.totalPages !== null && nextP >= props.totalPages) return null
  return pageUrlFor(nextP)
})
const thumbnailUrl = (page: number) => authUrl(`${API_BASE_URL}/manga/${props.media.id}/page/${page}?thumbnail=true`)

const totalPagesList = computed(() => {
  if (!props.totalPages) return []
  return Array.from({ length: props.totalPages }, (_, i) => i)
})

const setPage = (page: number) => {
  const maximum = props.totalPages ? props.totalPages - 1 : Number.MAX_SAFE_INTEGER
  emit('update:currentPage', Math.max(0, Math.min(page, maximum)))
}

const previousPage = () => {
  if (props.currentPage === 0 && props.hasPreviousBatch) { emit('boundary', -1); return }
  if (readMode.value === 'webtoon') {
    if (webtoonContainerRef.value) {
      webtoonContainerRef.value.scrollBy({ top: -window.innerHeight * 0.7, behavior: 'smooth' })
    }
    return
  }
  setPage(props.currentPage - stepSize.value)
}

const nextPage = () => {
  if (props.totalPages && props.currentPage + stepSize.value >= props.totalPages && props.hasNextBatch) { emit('boundary', 1); return }
  if (readMode.value === 'webtoon') {
    if (webtoonContainerRef.value) {
      webtoonContainerRef.value.scrollBy({ top: window.innerHeight * 0.7, behavior: 'smooth' })
    }
    return
  }
  const maximum = props.totalPages ? props.totalPages - 1 : Number.MAX_SAFE_INTEGER
  if (props.totalPages === null || props.currentPage < maximum) {
    setPage(props.currentPage + stepSize.value)
  }
}

const setReadMode = (mode: MangaReadMode) => {
  readMode.value = mode
  localStorage.setItem(modeKey, mode)
  resetZoom()
  if (mode === 'webtoon') {
    nextTick(() => {
      scrollWebtoonToPage(props.currentPage)
    })
  }
}

const toggleRtl = () => {
  isRtl.value = !isRtl.value
  localStorage.setItem(`${preferencePrefix}_rtl`, String(isRtl.value))
}

const toggleShortcutGuide = () => {
  showShortcutGuide.value = !showShortcutGuide.value
}

const onSliderInput = (event: Event) => {
  const target = event.target as HTMLInputElement
  setPage(Number(target.value))
}

const isThumbnailActive = (index: number) => {
  if (readMode.value === 'double') {
    return index === props.currentPage || index === props.currentPage + 1
  }
  return index === props.currentPage
}

const totalWidth = computed(() => {
  if (!props.totalPages) return 0
  return THUMB_PAD * 2 + props.totalPages * THUMB_W + (props.totalPages - 1) * THUMB_GAP
})

const updateStripWidth = () => {
  if (thumbStripRef.value) {
    const w = thumbStripRef.value.clientWidth
    if (w > 0) stripContainerWidth.value = w
  }
}

watch(thumbStripRef, (el) => {
  if (stripResizeObserver) {
    stripResizeObserver.disconnect()
    stripResizeObserver = null
  }
  if (el && typeof ResizeObserver !== 'undefined') {
    stripResizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0) {
          stripContainerWidth.value = entry.contentRect.width
        }
      }
    })
    stripResizeObserver.observe(el)
    updateStripWidth()
  }
})

const visibleThumbnails = computed(() => {
  if (!props.totalPages) return []
  const containerWidth = stripContainerWidth.value
  const start = Math.max(0, Math.floor((thumbStripScroll.value - THUMB_PAD) / (THUMB_W + THUMB_GAP)) - THUMB_BUFFER)
  const end = Math.min(
    props.totalPages - 1,
    Math.ceil((thumbStripScroll.value + containerWidth - THUMB_PAD) / (THUMB_W + THUMB_GAP)) + THUMB_BUFFER,
  )
  return Array.from({ length: end - start + 1 }, (_, offset) => {
    const index = start + offset
    return { index, left: THUMB_PAD + index * (THUMB_W + THUMB_GAP) }
  })
})

const scrollToPage = (page: number, smooth = true) => {
  void nextTick(() => {
    const element = thumbStripRef.value
    if (!element) return
    const target = THUMB_PAD + page * (THUMB_W + THUMB_GAP) - element.clientWidth / 2 + THUMB_W / 2
    element.scrollTo({ left: Math.max(0, target), behavior: smooth ? 'smooth' : 'auto' })
  })
}

const onStripScroll = () => {
  if (scrollRafId !== null) return
  scrollRafId = requestAnimationFrame(() => {
    scrollRafId = null
    if (thumbStripRef.value) {
      thumbStripScroll.value = thumbStripRef.value.scrollLeft
    }
  })
}

const onStripMouseEnter = () => {
  emit('controlsHover', true)
}

const onStripMouseLeave = () => {
  if (isDragging) return
  onThumbLeave()
  emit('controlsHover', false)
}

const onDragStart = (event: MouseEvent) => {
  const element = thumbStripRef.value
  if (!element) return
  isDragging = true
  dragMoved = false
  dragStartX = event.clientX
  dragScrollStart = element.scrollLeft
  element.style.cursor = 'grabbing'
  element.style.scrollBehavior = 'auto'
  emit('controlsHover', true)
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

const onDragMove = (event: MouseEvent) => {
  if (!isDragging || !thumbStripRef.value) return
  const delta = event.clientX - dragStartX
  if (Math.abs(delta) > 3) dragMoved = true
  pendingDragScroll = dragScrollStart - delta
  if (dragRafId !== null) return
  dragRafId = requestAnimationFrame(() => {
    dragRafId = null
    if (thumbStripRef.value) {
      thumbStripRef.value.scrollLeft = pendingDragScroll
    }
  })
}

const onDragEnd = (event: MouseEvent) => {
  isDragging = false
  if (dragRafId !== null) {
    cancelAnimationFrame(dragRafId)
    dragRafId = null
  }
  if (thumbStripRef.value) {
    thumbStripRef.value.style.cursor = 'grab'
    thumbStripRef.value.style.scrollBehavior = ''
  }
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  const rect = thumbStripRef.value?.parentElement?.getBoundingClientRect()
  if (rect) {
    const isInside = event.clientX >= rect.left && event.clientX <= rect.right &&
                     event.clientY >= rect.top && event.clientY <= rect.bottom
    if (!isInside) {
      onThumbLeave()
      emit('controlsHover', false)
    }
  }
}

const onThumbClick = (page: number) => {
  if (!dragMoved) setPage(page)
}

const onThumbEnter = (page: number, event: MouseEvent) => {
  if (isDragging) return
  const target = event.currentTarget as HTMLElement
  window.clearTimeout(hoverTimer)
  hoverTimer = window.setTimeout(() => {
    if (isDragging) return
    hoverThumbIndex.value = page
    emit('controlsHover', true)
    const rect = target.getBoundingClientRect()
    const stripRect = thumbStripRef.value?.parentElement?.getBoundingClientRect()
    if (!stripRect) return
    hoverThumbX.value = rect.left + rect.width / 2 - stripRect.left
    hoverThumbY.value = rect.top - stripRect.top - 8
  }, 70)
}

const onThumbLeave = () => {
  window.clearTimeout(hoverTimer)
  hoverThumbIndex.value = -1
}

const onWheel = (event: WheelEvent) => {
  if (readMode.value === 'webtoon') {
    return
  }
  if (event.ctrlKey || event.metaKey) {
    handleZoomWheel(event)
    return
  }
  const now = Date.now()
  if (now - lastWheelAt < WHEEL_INTERVAL_MS) return
  const delta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX
  if (Math.abs(delta) < 8) return
  event.preventDefault()
  lastWheelAt = now
  delta > 0 ? nextPage() : previousPage()
}

const onWebtoonScroll = () => {
  if (isProgrammaticScroll || readMode.value !== 'webtoon' || webtoonScrollRafId !== null) return
  webtoonScrollRafId = requestAnimationFrame(() => {
    webtoonScrollRafId = null
    if (isProgrammaticScroll || readMode.value !== 'webtoon') return
    const container = webtoonContainerRef.value
    if (!container || !props.totalPages) return
    const containerTop = container.scrollTop + 100
    const children = container.children
    if (!children.length) return
    let low = 0
    let high = children.length - 1
    while (low < high) {
      const mid = Math.floor((low + high) / 2)
      const el = children[mid] as HTMLElement
      if (el.offsetTop + el.offsetHeight < containerTop) low = mid + 1
      else high = mid
    }
    if (low !== props.currentPage) {
      // Scrolling reports progress; it must not trigger the page-navigation watcher.
      scrollReportedPage = low
      emit('update:currentPage', low)
    }
  })
}

const scrollWebtoonToPage = (page: number) => {
  if (readMode.value !== 'webtoon') return
  const container = webtoonContainerRef.value
  const el = container?.children[page] as HTMLElement | undefined
  if (!container || !el) return
  isProgrammaticScroll = true
  window.clearTimeout(programmaticScrollTimer)
  // Only move the reader. scrollIntoView can also move the surrounding overlay.
  container.scrollTo({ top: el.offsetTop, behavior: 'auto' })
  programmaticScrollTimer = window.setTimeout(() => {
    isProgrammaticScroll = false
  }, 100)
}

const onViewerClick = () => {
  if (wasZoomDragging() || wasTouchGesture()) return
  emit('viewerClick')
}

// Compensate once per render when decoded dimensions above the viewport change.
let pendingAnchor: { container: HTMLDivElement; element: HTMLElement; top: number } | null = null
const imageBuffer = useReaderImageBuffer(update => {
  const container = webtoonContainerRef.value
  const element = container?.children[props.currentPage] as HTMLElement | undefined
  const anchor = !pendingAnchor && container && element && container.scrollTop > 0
    ? { container, element, top: element.offsetTop } : null
  if (anchor) pendingAnchor = anchor
  update()
  if (anchor) {
    void nextTick(() => {
      if (webtoonContainerRef.value === anchor.container && anchor.element.isConnected) {
        anchor.container.scrollTop += anchor.element.offsetTop - anchor.top
      }
      pendingAnchor = null
    })
  }
})
const pageDimensionsFor = (page: number): [number, number] => {
  const dimensions = props.pageDimensions[page]
  if (dimensions?.[0] && dimensions?.[1]) return dimensions
  const state = imageBuffer.states.get(pageUrlFor(page))
  return state?.width && state.height ? [state.width, state.height] : [2, 3]
}
const pageReady = (page: number) => imageBuffer.states.get(pageUrlFor(page))?.status === 'ready'
const pageFailed = (page: number) => imageBuffer.states.get(pageUrlFor(page))?.status === 'error'
const preloadAdjacentPages = () => {
  if (!props.totalPages) return
  const page = props.currentPage
  // Six pages ahead, two behind; prioritize the visible spread before speculation.
  const indices = [page, page + 1, page + 2, page - 1, page + 3, page + 4, page - 2, page + 5, page + 6]
  imageBuffer.requestWindow(indices.filter(p => p >= 0 && p < props.totalPages!).map(pageUrlFor))
}
watch(() => [props.totalPages, readMode.value, props.imagePages?.map(item => item.id).join(',')], preloadAdjacentPages)
watch(() => props.showControls, visible => { if (!visible) showShortcutGuide.value = false })
defineExpose({ nextPage, previousPage, stepSize })

watch(() => props.currentPage, page => {
  if (readMode.value !== 'webtoon') {
    resetZoom()
  } else if (page === scrollReportedPage) {
    scrollReportedPage = null
  } else {
    scrollReportedPage = null
    void nextTick(() => scrollWebtoonToPage(page))
  }
  scrollToPage(page)
  preloadAdjacentPages()
}, { immediate: true })
watch(() => props.totalPages, (total, previousTotal) => {
  if (!total) return
  scrollToPage(props.currentPage, false)
  if (readMode.value === 'webtoon' && !previousTotal) {
    void nextTick(() => scrollWebtoonToPage(props.currentPage))
  }
})
watch(() => props.media.id, () => {
  if (props.imagePages) return
  imageBuffer.clear()
  preloadAdjacentPages()
  scrollReportedPage = null
  hoverThumbIndex.value = -1
  thumbStripScroll.value = 0
  scrollToPage(props.currentPage, false)
})

watch(isStripOpen, (open) => {
  if (open) {
    nextTick(() => {
      updateStripWidth()
      scrollToPage(props.currentPage, false)
    })
  }
})

onMounted(() => {
  updateStripWidth()
  window.addEventListener('resize', updateStripWidth, { passive: true })
})

onBeforeUnmount(() => {
  imageBuffer.dispose()
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  window.removeEventListener('resize', updateStripWidth)
  window.clearTimeout(programmaticScrollTimer)
  window.clearTimeout(hoverTimer)
  if (scrollRafId !== null) cancelAnimationFrame(scrollRafId)
  if (webtoonScrollRafId !== null) cancelAnimationFrame(webtoonScrollRafId)
  if (dragRafId !== null) cancelAnimationFrame(dragRafId)
  if (stripResizeObserver) {
    stripResizeObserver.disconnect()
    stripResizeObserver = null
  }
})
</script>

<template>
  <div class="flex-1 min-h-0 flex flex-col bg-black overflow-hidden relative">
    <div
      class="flex-1 min-h-0 flex items-center justify-center w-full relative group overflow-hidden"
      @wheel="onWheel"
      @click="onViewerClick"
      @dblclick="emit('viewerDoubleClick')"
    >
      <!-- Left Prev Button -->
      <button
        @click.stop="previousPage"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 -translate-x-6 pointer-events-none'
            : 'opacity-0 -translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="he-page-nav absolute left-5 z-20 grid size-12 place-items-center rounded-full bg-black/60 text-white/80 transition-[opacity,transform,background-color,color] duration-200 ease-out hover:bg-black/80 hover:text-white focus-ring"
        title="上一页" aria-label="上一页" :tabindex="showControls ? 0 : -1"
      >
        <ChevronLeft :size="26" aria-hidden="true" />
      </button>

      <!-- Webtoon Continuous Scroll Mode -->
      <div
        v-if="readMode === 'webtoon'"
        ref="webtoonContainerRef"
        style="overflow-anchor: none"
        class="w-full h-full overflow-y-auto custom-scrollbar flex flex-col items-center py-6 px-2 select-none"
        @scroll="onWebtoonScroll"
      >
        <div
          v-for="pageIndex in totalPagesList"
          :key="imagePages?.[pageIndex]?.id ?? pageIndex"
          :id="`webtoon-page-${pageIndex}`"
          class="he-reader-page w-full max-w-[840px] shrink-0 my-1 relative group bg-white/5"
          :style="{ aspectRatio: `${pageDimensionsFor(pageIndex)[0]} / ${pageDimensionsFor(pageIndex)[1]}` }"
        >
          <img
            v-if="pageReady(pageIndex)"
            :src="pageUrlFor(pageIndex)"
            :width="pageDimensionsFor(pageIndex)[0]"
            :height="pageDimensionsFor(pageIndex)[1]"
            loading="eager"
            decoding="sync"
            class="w-full h-full object-contain block rounded-sm"
            :alt="imagePages?.[pageIndex]?.title || `第 ${pageIndex + 1} 页`"
          />
          <div v-else class="absolute inset-0 flex flex-col items-center justify-center gap-3 text-meta text-white/60" role="status">
            <template v-if="pageFailed(pageIndex)">
              <span>图片加载失败</span>
              <button type="button" class="h-10 rounded-lg bg-white/10 px-4 text-body font-medium text-white transition-colors hover:bg-white/15 focus-ring pointer-coarse:h-11" @click.stop="imageBuffer.retry(pageUrlFor(pageIndex))">重新加载</button>
            </template>
            <span v-else>正在加载第 {{ pageIndex + 1 }} {{ imagePages ? '张' : '页' }}…</span>
          </div>
          <div v-if="showControls" class="pointer-events-none absolute right-2 top-2 inline-flex h-6 items-center rounded-md bg-black/60 px-1.5 text-caption font-medium tabular-nums text-white/90 opacity-0 transition-opacity group-hover:opacity-100">
            {{ pageIndex + 1 }} / {{ totalPages }}
          </div>
        </div>
      </div>

      <!-- Single / Double Page Canvas Mode -->
      <div
        v-else
        ref="imageContainerRef"
        class="w-full h-full flex items-center justify-center overflow-hidden select-none"
        :style="{ cursor: isZoomed ? (isZoomPanning ? 'grabbing' : 'grab') : 'default' }"
        @mousedown="onZoomMouseDown"
        @touchstart="onTouchStart" @touchmove="onTouchMove" @touchend="onTouchEnd" @touchcancel="onTouchEnd"
        style="touch-action: none"
      >
        <!-- Single Mode -->
        <div
          v-if="readMode === 'single'"
          class="w-full h-full flex items-center justify-center"
          :style="{
            transform: `translate3d(${zoomTx}px, ${zoomTy}px, 0px) scale(${zoomScale})`,
            transition: isZoomPanning ? 'none' : 'transform 0.15s ease-out',
          }"
        >
          <img
            :src="pageUrl"
            class="h-full w-full object-contain pointer-events-none"
            :alt="media.title"
          />
        </div>

        <!-- Double Page Mode -->
        <div
          v-else-if="readMode === 'double'"
          class="w-full h-full flex items-center justify-center gap-1 sm:gap-2 px-2"
          :style="{
            transform: `translate3d(${zoomTx}px, ${zoomTy}px, 0px) scale(${zoomScale})`,
            transition: isZoomPanning ? 'none' : 'transform 0.15s ease-out',
          }"
        >
          <template v-if="isRtl">
            <img
              v-if="secondPageUrl"
              :src="secondPageUrl"
              class="h-full max-w-[50%] object-contain pointer-events-none"
              :alt="`第 ${currentPage + 2} 页`"
            />
            <img
              :src="pageUrl"
              class="h-full max-w-[50%] object-contain pointer-events-none"
              :alt="`第 ${currentPage + 1} 页`"
            />
          </template>
          <template v-else>
            <img
              :src="pageUrl"
              class="h-full max-w-[50%] object-contain pointer-events-none"
              :alt="`第 ${currentPage + 1} 页`"
            />
            <img
              v-if="secondPageUrl"
              :src="secondPageUrl"
              class="h-full max-w-[50%] object-contain pointer-events-none"
              :alt="`第 ${currentPage + 2} 页`"
            />
          </template>
        </div>
      </div>

      <!-- Right Next Button -->
      <button
        @click.stop="nextPage"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 translate-x-6 pointer-events-none'
            : 'opacity-0 translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="he-page-nav absolute right-5 z-20 grid size-12 place-items-center rounded-full bg-black/60 text-white/80 transition-[opacity,transform,background-color,color] duration-200 ease-out hover:bg-black/80 hover:text-white focus-ring"
        title="下一页" aria-label="下一页" :tabindex="showControls ? 0 : -1"
      >
        <ChevronRight :size="26" aria-hidden="true" />
      </button>

      <!-- Bottom Floating Control Pill (Slider + Mode Switcher + Shortcuts) -->
      <div
        :class="showControls || !clickOnlyControls ? 'opacity-100' : 'opacity-0 pointer-events-none'"
        :inert="!showControls && clickOnlyControls"
        class="he-manga-controls absolute left-1/2 z-20 flex w-[min(640px,calc(100%-2rem))] select-none flex-col gap-2 rounded-2xl bg-black/75 p-2.5 text-white ring-1 ring-inset ring-white/10 transition-[transform,opacity] duration-200 ease-out sm:px-3"
        :style="{
          bottom: 'calc(12px + env(safe-area-inset-bottom))',
          transform: `translate3d(-50%, ${isStripOpen ? '-184px' : (showControls || !clickOnlyControls ? '0px' : '12px')}, 0)`,
        }"
        style="will-change: transform, opacity;"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        @click.stop
      >
        <div class="flex items-center justify-between gap-2">
          <!-- Reading Mode Switcher -->
          <div class="flex items-center gap-0.5 rounded-lg bg-white/8 p-0.5" role="group" aria-label="阅读模式">
            <button
              type="button"
              @click="setReadMode('single')"
              class="he-reader-seg"
              :class="readMode === 'single' ? 'bg-white/15 text-white' : 'text-white/65 hover:text-white'"
              title="单页模式" :aria-pressed="readMode === 'single'"
            >
              <Square :size="14" aria-hidden="true" />
              <span class="hidden sm:inline">单页</span>
            </button>
            <button
              type="button"
              @click="setReadMode('double')"
              class="he-reader-seg"
              :class="readMode === 'double' ? 'bg-white/15 text-white' : 'text-white/65 hover:text-white'"
              title="双页跨页模式" :aria-pressed="readMode === 'double'"
            >
              <Columns2 :size="14" aria-hidden="true" />
              <span class="hidden sm:inline">双页</span>
            </button>
            <button
              type="button"
              @click="setReadMode('webtoon')"
              class="he-reader-seg"
              :class="readMode === 'webtoon' ? 'bg-white/15 text-white' : 'text-white/65 hover:text-white'"
              title="连续卷轴模式 (条漫)" :aria-pressed="readMode === 'webtoon'"
            >
              <ScrollText :size="14" aria-hidden="true" />
              <span class="hidden sm:inline">卷轴</span>
            </button>
          </div>

          <!-- In Double Mode: RTL / LTR Toggle -->
          <button
            v-if="readMode === 'double'"
            type="button"
            @click="toggleRtl"
            class="he-reader-btn px-2.5 text-meta font-medium text-white/80 hover:bg-white/10 hover:text-white"
            :title="isRtl ? '日漫从右往左翻 (RTL)' : '普通从左往右翻 (LTR)'"
          >
            {{ isRtl ? '从右往左' : '从左往右' }}
          </button>

          <button v-if="imagePages && hasNextBatch" type="button" title="加载后续图片" class="he-reader-btn px-2.5 text-meta font-medium text-white/80 hover:bg-white/10 hover:text-white" @click="emit('loadMore')">更多图片</button>

          <!-- Middle Page info -->
          <div class="ml-auto flex items-baseline gap-2 whitespace-nowrap px-1 tabular-nums">
            <span class="text-body font-medium text-white">{{ progressText }}</span>
            <span class="text-meta text-white/60">{{ progressPercent }}%</span>
          </div>

          <!-- Shortcut Guide Toggle Button -->
          <button
            type="button"
            @click="toggleShortcutGuide"
            class="he-reader-btn w-8 text-white/70 hover:bg-white/10 hover:text-white"
            :class="{ 'bg-white/15 text-white': showShortcutGuide }"
            title="快捷键指南" aria-label="快捷键指南" :aria-expanded="showShortcutGuide" data-keyboard-guide
          >
            <Keyboard :size="16" aria-hidden="true" />
          </button>

          <!-- Toggle Thumbnail Strip Button -->
          <button
            v-if="!imagePages && totalPages && totalPages > 0"
            type="button"
            @click="toggleStripCollapsed"
            class="he-reader-btn gap-1.5 px-2.5 text-meta font-medium text-white/70 hover:bg-white/10 hover:text-white"
            :class="{ 'bg-white/15 text-white': isStripOpen }"
            :title="isStripOpen ? '收起底部预览长条' : '展开底部预览长条'"
          >
            <GalleryHorizontal :size="15" aria-hidden="true" />
            <span class="hidden sm:inline">{{ isStripOpen ? '收起目录' : '展开目录' }}</span>
          </button>
        </div>

        <!-- Interactive Progress Slider -->
        <div class="relative flex items-center px-1">
          <input
            type="range"
            :min="0"
            :max="Math.max(0, (totalPages || 1) - 1)"
            :step="stepSize"
            :value="currentPage"
            @input="onSliderInput"
            class="he-reader-slider h-5 w-full cursor-pointer"
            :style="{ '--fill': `${Math.min(100, Math.max(0, currentPage / Math.max(1, (totalPages || 1) - 1) * 100))}%` }"
            :title="`第 ${currentPage + 1} 页`"
          />
        </div>
      </div>

      <!-- Shortcut Guide Popover -->
      <div
        v-if="showShortcutGuide"
        class="absolute z-30 w-80 max-w-[calc(100%-2rem)] select-none rounded-2xl bg-black/90 p-4 text-meta text-white/85 ring-1 ring-inset ring-white/12 animate-fluid-entrance"
        :style="{
          bottom: isStripOpen ? '280px' : '96px',
          left: '50%',
          transform: 'translateX(-50%)',
          transition: 'bottom 240ms var(--ease-out)',
        }"
        @click.stop
      >
        <div class="mb-3 flex items-center justify-between">
          <span class="flex items-center gap-2 text-body font-medium text-white">
            <Keyboard :size="16" class="text-white/60" aria-hidden="true" />
            阅读器快捷键
          </span>
          <button type="button" class="he-reader-btn w-8 text-white/60 hover:bg-white/10 hover:text-white" aria-label="关闭快捷键指南" title="关闭" @click="showShortcutGuide = false"><X :size="16" aria-hidden="true" /></button>
        </div>
        <div class="space-y-2.5">
          <div class="flex items-center justify-between">
            <span class="text-white/65">翻页 / 换页</span>
            <kbd class="he-reader-kbd">← / →</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/65">滚轮翻页</span>
            <kbd class="he-reader-kbd">鼠标滚轮</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/65">画面缩放</span>
            <kbd class="he-reader-kbd">Ctrl + 滚轮 / + -</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/65">适应屏幕 / 重置</span>
            <kbd class="he-reader-kbd">0 / 双击</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/65">拖拽平移</span>
            <kbd class="he-reader-kbd">按住鼠标左键</kbd>
          </div>
        </div>
      </div>

      <!-- Zoom Controls Floating Pill (Single / Double Mode) -->
      <div
        v-if="readMode !== 'webtoon'"
        :class="showControls
          ? 'opacity-100'
          : 'opacity-0 pointer-events-none'"
        :inert="!showControls"
        class="he-manga-zoom absolute right-6 z-20 flex select-none items-center gap-0.5 rounded-2xl bg-black/75 p-1 text-white/80 ring-1 ring-inset ring-white/10 transition-[transform,opacity] duration-200 ease-out"
        :style="{
          bottom: 'calc(12px + env(safe-area-inset-bottom))',
          transform: `translate3d(0, ${isStripOpen ? '-184px' : (showControls ? '0px' : '12px')}, 0)`,
        }"
        style="will-change: transform, opacity;"
        @click.stop
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
      >
        <button
          @click="zoomOut()"
          :disabled="zoomScale <= 1"
          class="he-reader-btn w-8 hover:bg-white/10 hover:text-white disabled:pointer-events-none disabled:opacity-35"
          aria-label="缩小"
          title="缩小 (Ctrl + 滚轮向下 / 快捷键: -)"
        >
          <ZoomOut :size="16" aria-hidden="true" />
        </button>

        <button
          @click="resetZoom"
          class="he-reader-btn min-w-14 px-2 text-meta font-medium tabular-nums hover:bg-white/10 hover:text-white"
          :class="isZoomed ? 'text-white' : 'text-white/65'"
          title="重置缩放 (快捷键: 0)"
        >
          {{ zoomPercent }}%
        </button>

        <button
          @click="zoomIn()"
          :disabled="zoomScale >= 5"
          class="he-reader-btn w-8 hover:bg-white/10 hover:text-white disabled:pointer-events-none disabled:opacity-35"
          aria-label="放大"
          title="放大 (Ctrl + 滚轮向上 / 快捷键: +)"
        >
          <ZoomIn :size="16" aria-hidden="true" />
        </button>

        <button
          v-if="isZoomed"
          @click="resetZoom"
          class="he-reader-btn w-8 text-white/65 hover:bg-white/10 hover:text-white"
          aria-label="适应屏幕"
          title="适应屏幕 (快捷键: 0)"
        >
          <RotateCcw :size="15" aria-hidden="true" />
        </button>
      </div>
    </div>

    <!-- Bottom Thumbnail Strip Bar -->
    <div
      v-if="!imagePages && totalPages && totalPages > 0"
      :class="isStripOpen
        ? 'translate-y-0 opacity-100'
        : 'translate-y-full opacity-0 pointer-events-none'"
      :inert="!isStripOpen"
      class="he-manga-strip absolute inset-x-0 bottom-0 z-30 flex select-none flex-col border-t border-white/10 bg-black/90 transition-[transform,opacity] duration-200 ease-out"
      style="will-change: transform, opacity;"
      @click.stop
      @mouseenter="onStripMouseEnter"
      @mouseleave="onStripMouseLeave"
    >
      <div class="flex items-center justify-between px-6 py-0.5 text-meta">
        <div class="flex items-center gap-2 tabular-nums">
          <span class="font-medium text-white/85">预览目录</span>
          <span class="text-white/55">共 {{ totalPages }} 页 · 第 {{ currentPage + 1 }} 页</span>
        </div>
        <button
          type="button"
          @click="toggleStripCollapsed"
          class="he-reader-btn !h-6 gap-1 px-2 text-meta text-white/65 hover:bg-white/10 hover:text-white"
          title="收起预览目录"
        >
          <ChevronDown :size="14" aria-hidden="true" />
          <span>收起</span>
        </button>
      </div>

      <div
        v-if="hoverThumbIndex >= 0"
        class="pointer-events-none absolute z-50 rounded-2xl bg-black/95 p-1 ring-1 ring-inset ring-white/15"
        :style="{ width: '200px', height: '268px', left: `${hoverThumbX}px`, top: `${hoverThumbY}px`, transform: 'translate(-50%, -100%)' }"
      >
        <img :src="thumbnailUrl(hoverThumbIndex)" class="h-full w-full rounded-lg object-contain" alt="" />
        <div class="absolute inset-x-1 bottom-1 rounded-b-lg bg-black/70 py-0.5 text-center text-caption font-medium tabular-nums text-white/90">
          第 {{ hoverThumbIndex + 1 }} 页
        </div>
      </div>

      <div
        ref="thumbStripRef"
        class="overflow-x-auto py-2 custom-scrollbar select-none"
        style="cursor: grab"
        @scroll="onStripScroll"
        @mousedown.prevent="onDragStart"
      >
        <div :style="{ width: `${totalWidth}px`, height: `${THUMB_H + 4}px`, position: 'relative' }">
          <div
            v-for="item in visibleThumbnails"
            :key="item.index"
            class="absolute top-0.5 cursor-pointer overflow-hidden rounded-lg border-2 transition-colors duration-150"
            style="contain: layout paint style;"
            :class="isThumbnailActive(item.index)
              ? 'z-10 border-accent bg-accent/10'
              : 'border-transparent bg-white/5 hover:border-white/30'"
            :style="{ left: `${item.left}px`, width: `${THUMB_W}px`, height: `${THUMB_H}px` }"
            @click="onThumbClick(item.index)"
            @mouseenter="onThumbEnter(item.index, $event)"
            @mouseleave="onThumbLeave"
          >
            <img
              :src="thumbnailUrl(item.index)"
              loading="lazy"
              decoding="async"
              class="h-full w-full object-cover"
              :class="isThumbnailActive(item.index) ? '' : 'opacity-80 hover:opacity-100'"
              draggable="false"
              alt=""
            />
            <div
              class="absolute inset-x-0 bottom-0 py-0.5 text-center text-caption font-medium tabular-nums"
              :class="isThumbnailActive(item.index) ? 'bg-accent text-on-accent' : 'bg-black/65 text-white/85'"
            >
              {{ item.index + 1 }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.he-reader-seg {
  display: inline-flex;
  height: 32px;
  align-items: center;
  gap: 6px;
  border-radius: 6px;
  padding-inline: 10px;
  font-size: var(--text-meta, 0.8125rem);
  font-weight: 500;
  transition: background-color 120ms var(--ease-out), color 120ms var(--ease-out);
}
.he-reader-btn {
  display: inline-flex;
  height: 32px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  transition: background-color 120ms var(--ease-out), color 120ms var(--ease-out);
}
.he-reader-kbd {
  display: inline-flex;
  height: 22px;
  align-items: center;
  border-radius: 6px;
  border: 1px solid rgb(255 255 255 / 0.15);
  background: rgb(255 255 255 / 0.08);
  padding-inline: 6px;
  font-size: 0.75em;
  color: rgb(255 255 255 / 0.85);
}
.he-reader-slider {
  appearance: none;
  -webkit-appearance: none;
  background: transparent;
}
.he-reader-slider::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 4px;
  background: linear-gradient(to right, rgb(var(--color-accent)) var(--fill, 0%), rgb(255 255 255 / 0.2) var(--fill, 0%));
}
.he-reader-slider::-moz-range-track {
  height: 4px;
  border-radius: 4px;
  background: linear-gradient(to right, rgb(var(--color-accent)) var(--fill, 0%), rgb(255 255 255 / 0.2) var(--fill, 0%));
}
.he-reader-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  margin-top: -5px;
  border-radius: 9999px;
  background: #fff;
  box-shadow: 0 0 0 3px rgb(var(--color-accent) / 0.45);
}
.he-reader-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border: 0;
  border-radius: 9999px;
  background: #fff;
  box-shadow: 0 0 0 3px rgb(var(--color-accent) / 0.45);
}
.he-reader-slider:focus-visible { outline: 2px solid rgb(var(--color-accent)); outline-offset: 2px; border-radius: 4px; }
@media (max-width: 899px) {
  .he-manga-controls > div:first-child { flex-wrap: wrap; gap: 4px; }
  .he-manga-controls button { min-height: 44px; min-width: 44px; }
  .he-manga-controls input[type="range"] { min-height: 30px; }
  [data-keyboard-guide] { display: none; }
  .he-manga-zoom { right: 12px; top: calc(140px + env(safe-area-inset-top)); bottom: auto !important; transform: none !important; }
  .he-manga-zoom button { min-height: 44px; min-width: 44px; }
  .he-manga-strip { padding-bottom: env(safe-area-inset-bottom); }
  .he-manga-strip button { min-height: 44px; }
  .he-page-nav.left-5 { left: 8px; width: 44px; height: 44px; }
  .he-page-nav.right-5 { right: 8px; width: 44px; height: 44px; }
}
</style>
