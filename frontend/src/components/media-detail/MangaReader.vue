<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { API_BASE_URL, authUrl } from '../../config'
import type { Media } from '../../types'

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
}>()

const thumbStripRef = ref<HTMLDivElement | null>(null)
const thumbStripScroll = ref(0)
const hoverThumbIndex = ref(-1)
const hoverThumbX = ref(0)
const hoverThumbY = ref(0)
let isDragging = false
let dragStartX = 0
let dragScrollStart = 0
let dragMoved = false
let lastWheelAt = 0

const THUMB_W = 110
const THUMB_H = 148
const THUMB_GAP = 12
const THUMB_PAD = 24
const THUMB_BUFFER = 5
const WHEEL_INTERVAL_MS = 320

const pageUrl = computed(() => authUrl(`${API_BASE_URL}/manga/${props.media.id}/page/${props.currentPage}`))
const thumbnailUrl = (page: number) => authUrl(`${API_BASE_URL}/manga/${props.media.id}/page/${page}?thumbnail=true`)

const setPage = (page: number) => {
  const maximum = props.totalPages ? props.totalPages - 1 : Number.MAX_SAFE_INTEGER
  emit('update:currentPage', Math.max(0, Math.min(page, maximum)))
}
const previousPage = () => setPage(props.currentPage - 1)
const nextPage = () => {
  if (props.totalPages === null || props.currentPage < props.totalPages - 1) setPage(props.currentPage + 1)
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

const onDragStart = (event: MouseEvent) => {
  const element = thumbStripRef.value
  if (!element) return
  isDragging = true
  dragMoved = false
  dragStartX = event.clientX
  dragScrollStart = element.scrollLeft
  element.style.cursor = 'grabbing'
  element.style.scrollBehavior = 'auto'
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

const onDragMove = (event: MouseEvent) => {
  if (!isDragging || !thumbStripRef.value) return
  const delta = event.clientX - dragStartX
  if (Math.abs(delta) > 3) dragMoved = true
  thumbStripRef.value.scrollLeft = dragScrollStart - delta
}

const onDragEnd = () => {
  isDragging = false
  if (thumbStripRef.value) {
    thumbStripRef.value.style.cursor = 'grab'
    thumbStripRef.value.style.scrollBehavior = ''
  }
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
}

const onThumbClick = (page: number) => {
  if (!dragMoved) setPage(page)
}

const onThumbEnter = (page: number, event: MouseEvent) => {
  if (isDragging) return
  hoverThumbIndex.value = page
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const stripRect = thumbStripRef.value?.parentElement?.getBoundingClientRect()
  if (!stripRect) return
  hoverThumbX.value = rect.left + rect.width / 2 - stripRect.left
  hoverThumbY.value = rect.top - stripRect.top - 8
}

const onWheel = (event: WheelEvent) => {
  const now = Date.now()
  if (now - lastWheelAt < WHEEL_INTERVAL_MS) return
  const delta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX
  if (Math.abs(delta) < 8) return
  event.preventDefault()
  lastWheelAt = now
  delta > 0 ? nextPage() : previousPage()
}

watch(() => props.currentPage, page => scrollToPage(page))
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
})
</script>

<template>
  <div class="flex-1 min-h-0 flex flex-col bg-black overflow-hidden relative">
    <div
      class="flex-1 min-h-0 flex items-center justify-center w-full relative group"
      @wheel="onWheel"
      @click="emit('viewerClick')"
      @dblclick="emit('viewerDoubleClick')"
    >
      <button
        @click.stop="previousPage"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 -translate-x-6 pointer-events-none'
            : 'opacity-0 -translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="absolute left-5 z-10 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300"
        title="上一页"
      >
        <ChevronLeft :size="34" class="mx-auto" />
      </button>

      <img :src="pageUrl" class="h-full w-full object-contain transition-opacity duration-300" :alt="media.title" />

      <button
        @click.stop="nextPage"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 translate-x-6 pointer-events-none'
            : 'opacity-0 translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="absolute right-5 z-10 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300"
        title="下一页"
      >
        <ChevronRight :size="34" class="mx-auto" />
      </button>

      <div
        :class="showControls || !clickOnlyControls ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3 pointer-events-none'"
        class="absolute bottom-6 left-1/2 z-20 w-[min(520px,calc(100%-2rem))] -translate-x-1/2 rounded-2xl bg-black/60 backdrop-blur-md border border-white/10 px-4 py-3 shadow-2xl transition-all duration-300"
        @click.stop
      >
        <div class="flex items-center justify-between gap-4 text-sm font-mono tracking-widest">
          <p class="text-white/70">PAGE <span class="text-white/95 font-bold ml-1">{{ progressText }}</span></p>
          <p class="font-bold text-purple-200">{{ progressPercent }}%</p>
        </div>
        <div class="mt-2 h-1.5 rounded-full bg-white/10 overflow-hidden">
          <div class="h-full bg-purple-300 transition-all duration-300" :style="{ width: `${progressPercent}%` }"></div>
        </div>
      </div>
    </div>

    <div
      v-if="totalPages && totalPages > 0"
      :class="showControls || !clickOnlyControls
        ? 'translate-y-0 opacity-100 max-h-[220px] border-t'
        : 'translate-y-full opacity-0 pointer-events-none max-h-0 overflow-hidden border-t-0'"
      class="shrink-0 border-white/10 bg-[#0c0c0e]/95 relative z-30 transition-all duration-500 ease-in-out flex flex-col"
      @click.stop
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
            :class="item.index === currentPage
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
              :class="item.index === currentPage ? 'brightness-110' : 'hover:brightness-110'"
              draggable="false"
              alt="Page thumbnail"
            />
            <div
              class="absolute bottom-0 inset-x-0 rounded-b-[10px] py-0.5 text-[10px] font-black text-center"
              :class="item.index === currentPage ? 'bg-accent/80 text-white' : 'bg-black/60 text-white/75'"
            >
              {{ item.index + 1 }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
