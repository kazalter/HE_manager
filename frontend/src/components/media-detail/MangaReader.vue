<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  ChevronLeft,
  ChevronRight,
  Columns2,
  Keyboard,
  RotateCcw,
  ScrollText,
  Square,
  ZoomIn,
  ZoomOut,
} from 'lucide-vue-next'
import { API_BASE_URL, authUrl } from '../../config'
import type { Media } from '../../types'
import { useImageViewerZoom } from '../../composables/useImageViewerZoom'

export type MangaReadMode = 'single' | 'double' | 'webtoon'

const props = defineProps<{
  media: Media
  currentPage: number
  totalPages: number | null
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
}>()

const readMode = ref<MangaReadMode>(
  (localStorage.getItem('he_manga_read_mode') as MangaReadMode) || 'single'
)
const isRtl = ref(localStorage.getItem('he_manga_rtl') === 'true')
const showShortcutGuide = ref(false)

const thumbStripRef = ref<HTMLDivElement | null>(null)
const imageContainerRef = ref<HTMLDivElement | null>(null)
const webtoonContainerRef = ref<HTMLDivElement | null>(null)
const thumbStripScroll = ref(0)
const hoverThumbIndex = ref(-1)
const hoverThumbX = ref(0)
const hoverThumbY = ref(0)
let isDragging = false
let dragStartX = 0
let dragScrollStart = 0
let dragMoved = false
let lastWheelAt = 0
let isProgrammaticScroll = false
let programmaticScrollTimer: number | undefined

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
} = useImageViewerZoom(imageContainerRef)

const THUMB_W = 110
const THUMB_H = 148
const THUMB_GAP = 12
const THUMB_PAD = 24
const THUMB_BUFFER = 5
const WHEEL_INTERVAL_MS = 320

const stepSize = computed(() => (readMode.value === 'double' ? 2 : 1))

const pageUrlFor = (page: number) => authUrl(`${API_BASE_URL}/manga/${props.media.id}/page/${page}`)
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
  if (readMode.value === 'webtoon') {
    if (webtoonContainerRef.value) {
      webtoonContainerRef.value.scrollBy({ top: -window.innerHeight * 0.7, behavior: 'smooth' })
    }
    return
  }
  setPage(props.currentPage - stepSize.value)
}

const nextPage = () => {
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
  localStorage.setItem('he_manga_read_mode', mode)
  resetZoom()
  if (mode === 'webtoon') {
    nextTick(() => {
      scrollWebtoonToPage(props.currentPage, false)
    })
  }
}

const toggleRtl = () => {
  isRtl.value = !isRtl.value
  localStorage.setItem('he_manga_rtl', String(isRtl.value))
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

const visibleThumbnails = computed(() => {
  if (!props.totalPages || !thumbStripRef.value) return []
  const containerWidth = thumbStripRef.value.clientWidth || 800
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
  if (thumbStripRef.value) thumbStripScroll.value = thumbStripRef.value.scrollLeft
}

const onStripMouseEnter = () => {
  emit('controlsHover', true)
}

const onStripMouseLeave = () => {
  if (isDragging) return
  hoverThumbIndex.value = -1
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
  thumbStripRef.value.scrollLeft = dragScrollStart - delta
}

const onDragEnd = (event: MouseEvent) => {
  isDragging = false
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
      hoverThumbIndex.value = -1
      emit('controlsHover', false)
    }
  }
}

const onThumbClick = (page: number) => {
  if (!dragMoved) setPage(page)
}

const onThumbEnter = (page: number, event: MouseEvent) => {
  if (isDragging) return
  hoverThumbIndex.value = page
  emit('controlsHover', true)
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const stripRect = thumbStripRef.value?.parentElement?.getBoundingClientRect()
  if (!stripRect) return
  hoverThumbX.value = rect.left + rect.width / 2 - stripRect.left
  hoverThumbY.value = rect.top - stripRect.top - 8
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
  if (isProgrammaticScroll || readMode.value !== 'webtoon') return
  const container = webtoonContainerRef.value
  if (!container || !props.totalPages) return
  const containerTop = container.scrollTop + 100
  const children = container.children
  for (let i = 0; i < children.length; i++) {
    const el = children[i] as HTMLElement
    if (el.offsetTop + el.offsetHeight >= containerTop) {
      if (i !== props.currentPage) {
        emit('update:currentPage', i)
      }
      break
    }
  }
}

const scrollWebtoonToPage = (page: number, smooth = true) => {
  if (readMode.value !== 'webtoon') return
  const el = document.getElementById(`webtoon-page-${page}`)
  if (el) {
    isProgrammaticScroll = true
    window.clearTimeout(programmaticScrollTimer)
    el.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' })
    programmaticScrollTimer = window.setTimeout(() => {
      isProgrammaticScroll = false
    }, 450)
  }
}

const onViewerClick = () => {
  if (wasZoomDragging()) return
  emit('viewerClick')
}

watch(() => props.currentPage, page => {
  if (readMode.value !== 'webtoon') {
    resetZoom()
  } else if (!isProgrammaticScroll) {
    scrollWebtoonToPage(page)
  }
  scrollToPage(page)
})
watch(() => props.totalPages, total => {
  if (total) scrollToPage(props.currentPage, false)
})
watch(() => props.media.id, () => {
  hoverThumbIndex.value = -1
  thumbStripScroll.value = 0
  scrollToPage(props.currentPage, false)
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  window.clearTimeout(programmaticScrollTimer)
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
        class="absolute left-5 z-20 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300 cursor-pointer"
        title="上一页"
      >
        <ChevronLeft :size="34" class="mx-auto" />
      </button>

      <!-- Webtoon Continuous Scroll Mode -->
      <div
        v-if="readMode === 'webtoon'"
        ref="webtoonContainerRef"
        class="w-full h-full overflow-y-auto custom-scrollbar flex flex-col items-center py-6 px-2 select-none"
        @scroll="onWebtoonScroll"
      >
        <div
          v-for="pageIndex in totalPagesList"
          :key="pageIndex"
          :id="`webtoon-page-${pageIndex}`"
          class="w-full max-w-[840px] flex flex-col items-center my-1 relative group"
        >
          <img
            :src="pageUrlFor(pageIndex)"
            loading="lazy"
            decoding="async"
            class="w-full h-auto object-contain block shadow-2xl rounded-sm bg-neutral-900 min-h-[300px]"
            :alt="`第 ${pageIndex + 1} 页`"
          />
          <div class="absolute top-2 right-2 bg-black/75 backdrop-blur-md text-white/70 text-[11px] font-mono px-2 py-0.5 rounded-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
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
            class="h-full w-full object-contain pointer-events-none transition-opacity duration-300"
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
              class="h-full max-w-[50%] object-contain pointer-events-none transition-opacity duration-300 shadow-xl"
              :alt="`第 ${currentPage + 2} 页`"
            />
            <img
              :src="pageUrl"
              class="h-full max-w-[50%] object-contain pointer-events-none transition-opacity duration-300 shadow-xl"
              :alt="`第 ${currentPage + 1} 页`"
            />
          </template>
          <template v-else>
            <img
              :src="pageUrl"
              class="h-full max-w-[50%] object-contain pointer-events-none transition-opacity duration-300 shadow-xl"
              :alt="`第 ${currentPage + 1} 页`"
            />
            <img
              v-if="secondPageUrl"
              :src="secondPageUrl"
              class="h-full max-w-[50%] object-contain pointer-events-none transition-opacity duration-300 shadow-xl"
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
        class="absolute right-5 z-20 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300 cursor-pointer"
        title="下一页"
      >
        <ChevronRight :size="34" class="mx-auto" />
      </button>

      <!-- Bottom Floating Control Pill (Slider + Mode Switcher + Shortcuts) -->
      <div
        :class="showControls || !clickOnlyControls ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3 pointer-events-none'"
        class="absolute bottom-6 left-1/2 z-20 w-[min(620px,calc(100%-2rem))] -translate-x-1/2 rounded-2xl bg-black/75 backdrop-blur-xl border border-white/12 p-3 sm:px-4 sm:py-3 shadow-2xl transition-all duration-300 flex flex-col gap-2.5"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        @click.stop
      >
        <div class="flex items-center justify-between gap-3 text-xs">
          <!-- Reading Mode Switcher -->
          <div class="flex items-center rounded-xl bg-white/8 p-0.5 border border-white/10 text-white/70">
            <button
              type="button"
              @click="setReadMode('single')"
              class="flex items-center gap-1 px-2.5 py-1 rounded-lg transition-all font-medium cursor-pointer"
              :class="readMode === 'single' ? 'bg-accent text-white shadow-md font-bold' : 'hover:text-white hover:bg-white/5'"
              title="单页模式"
            >
              <Square :size="13" />
              <span>单页</span>
            </button>
            <button
              type="button"
              @click="setReadMode('double')"
              class="flex items-center gap-1 px-2.5 py-1 rounded-lg transition-all font-medium cursor-pointer"
              :class="readMode === 'double' ? 'bg-accent text-white shadow-md font-bold' : 'hover:text-white hover:bg-white/5'"
              title="双页跨页模式"
            >
              <Columns2 :size="13" />
              <span>双页</span>
            </button>
            <button
              type="button"
              @click="setReadMode('webtoon')"
              class="flex items-center gap-1 px-2.5 py-1 rounded-lg transition-all font-medium cursor-pointer"
              :class="readMode === 'webtoon' ? 'bg-accent text-white shadow-md font-bold' : 'hover:text-white hover:bg-white/5'"
              title="连续卷轴模式 (条漫)"
            >
              <ScrollText :size="13" />
              <span>卷轴</span>
            </button>
          </div>

          <!-- In Double Mode: RTL / LTR Toggle -->
          <button
            v-if="readMode === 'double'"
            type="button"
            @click="toggleRtl"
            class="px-2.5 py-1 rounded-lg bg-white/8 hover:bg-white/15 border border-white/10 text-[11px] font-mono font-bold text-white/80 transition-all cursor-pointer"
            :title="isRtl ? '日漫从右往左翻 (RTL)' : '普通从左往右翻 (LTR)'"
          >
            {{ isRtl ? '日漫 RTL' : '标准 LTR' }}
          </button>

          <!-- Middle Page info -->
          <div class="flex items-center gap-2 font-mono tracking-wider ml-auto text-white/70">
            <span>PAGE <b class="text-white font-bold">{{ progressText }}</b></span>
            <span class="text-accent font-bold text-xs">{{ progressPercent }}%</span>
          </div>

          <!-- Shortcut Guide Toggle Button -->
          <button
            type="button"
            @click="toggleShortcutGuide"
            class="w-7 h-7 rounded-lg flex items-center justify-center text-white/60 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            :class="{ 'bg-white/15 text-white': showShortcutGuide }"
            title="快捷键指南"
          >
            <Keyboard :size="15" />
          </button>
        </div>

        <!-- Interactive Progress Slider -->
        <div class="relative flex items-center group/slider">
          <input
            type="range"
            :min="0"
            :max="Math.max(0, (totalPages || 1) - 1)"
            :step="stepSize"
            :value="currentPage"
            @input="onSliderInput"
            class="w-full h-2 rounded-lg bg-white/15 appearance-none cursor-pointer accent-accent transition-all focus:outline-none"
            :title="`第 ${currentPage + 1} 页`"
          />
        </div>
      </div>

      <!-- Shortcut Guide Popover -->
      <div
        v-if="showShortcutGuide"
        class="absolute bottom-28 left-1/2 -translate-x-1/2 z-30 w-80 rounded-2xl bg-[#121216]/95 backdrop-blur-2xl border border-white/15 p-4 shadow-2xl text-xs text-white/85 animate-fluid-entrance"
        @click.stop
      >
        <div class="flex items-center justify-between pb-2 mb-2.5 border-b border-white/10">
          <span class="font-bold flex items-center gap-1.5 text-accent">
            <Keyboard :size="14" />
            阅读器快捷键指南
          </span>
          <button @click="showShortcutGuide = false" class="text-white/40 hover:text-white text-sm cursor-pointer">✕</button>
        </div>
        <div class="space-y-2 text-[11px]">
          <div class="flex items-center justify-between">
            <span class="text-white/50">翻页 / 换页</span>
            <kbd class="px-1.5 py-0.5 rounded bg-white/10 border border-white/15 font-mono">← / →</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/50">滚轮翻页</span>
            <kbd class="px-1.5 py-0.5 rounded bg-white/10 border border-white/15 font-mono">鼠标滚轮</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/50">画面缩放</span>
            <kbd class="px-1.5 py-0.5 rounded bg-white/10 border border-white/15 font-mono">Ctrl + 滚轮 / + -</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/50">适应屏幕 / 重置</span>
            <kbd class="px-1.5 py-0.5 rounded bg-white/10 border border-white/15 font-mono">0 / 双击</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/50">拖拽平移</span>
            <kbd class="px-1.5 py-0.5 rounded bg-white/10 border border-white/15 font-mono">按住鼠标左键</kbd>
          </div>
        </div>
      </div>

      <!-- Zoom Controls Floating Pill (Single / Double Mode) -->
      <div
        v-if="readMode !== 'webtoon'"
        :class="showControls || isZoomed
          ? 'opacity-100 translate-y-0'
          : 'opacity-0 translate-y-3 pointer-events-none'"
        class="absolute bottom-6 right-6 z-20 flex items-center gap-1 rounded-2xl bg-black/60 backdrop-blur-md border border-white/10 px-2 py-1.5 shadow-2xl transition-all duration-300 select-none text-white/80"
        @click.stop
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
      >
        <button
          @click="zoomOut()"
          :disabled="zoomScale <= 1"
          class="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-white/10 active:scale-95 disabled:opacity-30 disabled:pointer-events-none transition-all cursor-pointer"
          title="缩小 (Ctrl + 滚轮向下 / 快捷键: -)"
        >
          <ZoomOut :size="15" />
        </button>

        <button
          @click="resetZoom"
          class="px-2 py-1 rounded-lg text-xs font-mono font-bold hover:bg-white/10 hover:text-white transition-all cursor-pointer"
          :class="isZoomed ? 'text-accent' : 'text-white/60'"
          title="重置缩放 (快捷键: 0)"
        >
          {{ zoomPercent }}%
        </button>

        <button
          @click="zoomIn()"
          :disabled="zoomScale >= 5"
          class="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-white/10 active:scale-95 disabled:opacity-30 disabled:pointer-events-none transition-all cursor-pointer"
          title="放大 (Ctrl + 滚轮向上 / 快捷键: +)"
        >
          <ZoomIn :size="15" />
        </button>

        <button
          v-if="isZoomed"
          @click="resetZoom"
          class="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-white/10 text-white/60 hover:text-white transition-all cursor-pointer ml-0.5"
          title="适应屏幕 (快捷键: 0)"
        >
          <RotateCcw :size="13" />
        </button>
      </div>
    </div>

    <!-- Bottom Thumbnail Strip Bar -->
    <div
      v-if="totalPages && totalPages > 0"
      :class="showControls || !clickOnlyControls
        ? 'translate-y-0 opacity-100 max-h-[220px] border-t'
        : 'translate-y-full opacity-0 pointer-events-none max-h-0 overflow-hidden border-t-0'"
      class="shrink-0 border-white/10 bg-[#0c0c0e]/95 relative z-30 transition-all duration-500 ease-in-out flex flex-col"
      @click.stop
      @mouseenter="onStripMouseEnter"
      @mouseleave="onStripMouseLeave"
    >
      <div class="flex items-center justify-between text-xs font-semibold px-6 py-2 text-white/50">
        <span>预览目录 (共 {{ totalPages }} 页)</span>
        <span>当前第 {{ currentPage + 1 }} 页</span>
      </div>

      <div
        v-if="hoverThumbIndex >= 0"
        class="absolute z-50 pointer-events-none rounded-xl border border-white/15 bg-black/95 p-1 shadow-2xl"
        :style="{ width: '200px', height: '268px', left: `${hoverThumbX}px`, top: `${hoverThumbY}px`, transform: 'translate(-50%, -100%)' }"
      >
        <img :src="thumbnailUrl(hoverThumbIndex)" class="w-full h-full object-contain rounded-lg" alt="Preview" />
        <div class="absolute bottom-1 inset-x-1 bg-black/70 rounded-b-lg py-0.5 text-[10px] font-black text-center text-white/90">
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
            class="absolute top-0 cursor-pointer rounded-xl border-2 transition-all duration-200"
            :class="isThumbnailActive(item.index)
              ? 'border-accent shadow-[0_0_16px_rgba(129,140,248,0.5)] bg-accent/10 scale-105 z-10'
              : 'border-white/8 hover:border-white/25 bg-white/5'"
            :style="{ left: `${item.left}px`, width: `${THUMB_W}px`, height: `${THUMB_H}px` }"
            @click="onThumbClick(item.index)"
            @mouseenter="onThumbEnter(item.index, $event)"
            @mouseleave="hoverThumbIndex = -1"
          >
            <img
              :src="thumbnailUrl(item.index)"
              loading="lazy"
              class="w-full h-full object-cover rounded-[10px] transition-all duration-200"
              :class="isThumbnailActive(item.index) ? 'brightness-110' : 'hover:brightness-110'"
              draggable="false"
              alt="Page thumbnail"
            />
            <div
              class="absolute bottom-0 inset-x-0 rounded-b-[10px] py-0.5 text-[10px] font-black text-center"
              :class="isThumbnailActive(item.index) ? 'bg-accent/80 text-white' : 'bg-black/60 text-white/75'"
            >
              {{ item.index + 1 }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
