<script setup lang="ts">
import { ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, RotateCcw, ZoomIn, ZoomOut } from 'lucide-vue-next'
import type { Media } from '../../types'
import { useImageViewerZoom } from '../../composables/useImageViewerZoom'

const props = defineProps<{
  media: Media
  imageUrl: string
  showControls: boolean
  clickOnlyControls: boolean
}>()

const emit = defineEmits<{
  previous: []
  next: []
  viewerClick: []
  viewerDoubleClick: []
  controlsHover: [hovering: boolean]
}>()

const imageContainerRef = ref<HTMLDivElement | null>(null)
let lastWheelAt = 0

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

const onWheel = (event: WheelEvent) => {
  if (event.ctrlKey || event.metaKey) {
    handleZoomWheel(event)
    return
  }
  const now = Date.now()
  if (now - lastWheelAt < 320) return
  const delta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX
  if (Math.abs(delta) < 8) return
  event.preventDefault()
  lastWheelAt = now
  delta > 0 ? emit('next') : emit('previous')
}

const onViewerClick = () => {
  if (wasZoomDragging()) return
  emit('viewerClick')
}

watch(() => props.imageUrl, () => {
  resetZoom()
})
</script>

<template>
  <div
    class="flex-1 min-h-0 flex flex-col items-center bg-black overflow-hidden relative group"
    @wheel="onWheel"
    @click="onViewerClick"
    @dblclick="emit('viewerDoubleClick')"
  >
    <div class="flex-1 flex items-center justify-center w-full h-full relative overflow-hidden">
      <button
        @click.stop="emit('previous')"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 -translate-x-6 pointer-events-none'
            : 'opacity-0 -translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="absolute left-5 z-20 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300"
        title="上一项"
      >
        <ChevronLeft :size="34" class="mx-auto" />
      </button>

      <div
        ref="imageContainerRef"
        class="w-full h-full flex items-center justify-center overflow-hidden select-none"
        :style="{ cursor: isZoomed ? (isZoomPanning ? 'grabbing' : 'grab') : 'default' }"
        @mousedown="onZoomMouseDown"
      >
        <img
          :src="imageUrl"
          class="h-full w-full object-contain pointer-events-none transition-opacity duration-300"
          :style="{
            transform: `translate3d(${zoomTx}px, ${zoomTy}px, 0px) scale(${zoomScale})`,
            transition: isZoomPanning ? 'none' : 'transform 0.15s ease-out',
          }"
          :alt="media.title"
        />
      </div>

      <button
        @click.stop="emit('next')"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 translate-x-6 pointer-events-none'
            : 'opacity-0 translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="absolute right-5 z-20 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300"
        title="下一项"
      >
        <ChevronRight :size="34" class="mx-auto" />
      </button>

      <!-- Zoom Controls Floating Pill -->
      <div
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
  </div>
</template>
