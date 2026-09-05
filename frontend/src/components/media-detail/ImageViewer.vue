<script setup lang="ts">
import { ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, Loader2, RotateCcw, RotateCw, ZoomIn, ZoomOut } from 'lucide-vue-next'
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

const imgRef = ref<HTMLImageElement | null>(null)
const imageContainerRef = ref<HTMLDivElement | null>(null)
const isLoading = ref(true)
const rotation = ref(0)
const isActualSize = ref(false)
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
  setScale,
  handleZoomWheel,
  onMouseDown: onZoomMouseDown,
  wasDragging: wasZoomDragging,
} = useImageViewerZoom(imageContainerRef)

const rotateClockwise = () => {
  rotation.value = (rotation.value + 90) % 360
}

const resetAll = () => {
  resetZoom()
  rotation.value = 0
  isActualSize.value = false
}

const onImageLoad = () => {
  isLoading.value = false
}

const onImageError = () => {
  isLoading.value = false
}

const toggleActualSize = () => {
  if (isZoomed.value || isActualSize.value) {
    resetZoom()
    isActualSize.value = false
  } else {
    const img = imgRef.value
    const container = imageContainerRef.value
    if (img && container && img.naturalWidth && img.naturalHeight) {
      const isRotated90or270 = rotation.value % 180 !== 0
      const imgW = isRotated90or270 ? img.naturalHeight : img.naturalWidth
      const imgH = isRotated90or270 ? img.naturalWidth : img.naturalHeight
      const containerW = container.clientWidth
      const containerH = container.clientHeight
      const containScale = Math.min(containerW / imgW, containerH / imgH)
      if (containScale > 0) {
        const targetScale = 1 / containScale
        setScale(targetScale)
        isActualSize.value = true
        return
      }
    }
    setScale(2)
    isActualSize.value = true
  }
}

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
  isLoading.value = true
  resetAll()
})

watch(isZoomed, (val) => {
  if (!val) {
    isActualSize.value = false
  }
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
      <!-- Loading Skeleton Overlay -->
      <div
        v-if="isLoading"
        class="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/50 backdrop-blur-xs z-10 pointer-events-none transition-opacity duration-300"
      >
        <Loader2 class="w-8 h-8 text-accent animate-spin" />
        <span class="text-xs text-white/60 tracking-wider">正在加载图片...</span>
      </div>

      <!-- Left Prev Button -->
      <button
        @click.stop="emit('previous')"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 -translate-x-6 pointer-events-none'
            : 'opacity-0 -translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="absolute left-5 z-20 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300 cursor-pointer"
        title="上一项"
      >
        <ChevronLeft :size="34" class="mx-auto" />
      </button>

      <!-- Main Image Container -->
      <div
        ref="imageContainerRef"
        class="w-full h-full flex items-center justify-center overflow-hidden select-none"
        :style="{ cursor: isZoomed ? (isZoomPanning ? 'grabbing' : 'grab') : 'default' }"
        @mousedown="onZoomMouseDown"
      >
        <img
          ref="imgRef"
          :src="imageUrl"
          @load="onImageLoad"
          @error="onImageError"
          class="h-full w-full object-contain pointer-events-none transition-all duration-300"
          :class="isLoading ? 'opacity-0 scale-95' : 'opacity-100 scale-100'"
          :style="{
            transform: `translate3d(${zoomTx}px, ${zoomTy}px, 0px) scale(${zoomScale}) rotate(${rotation}deg)`,
            transition: isZoomPanning ? 'none' : 'transform 0.15s ease-out, opacity 0.3s ease-out',
          }"
          :alt="media.title"
        />
      </div>

      <!-- Right Next Button -->
      <button
        @click.stop="emit('next')"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 translate-x-6 pointer-events-none'
            : 'opacity-0 translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="absolute right-5 z-20 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300 cursor-pointer"
        title="下一项"
      >
        <ChevronRight :size="34" class="mx-auto" />
      </button>

      <!-- Floating Toolbar Pill -->
      <div
        :class="showControls || isZoomed || rotation !== 0
          ? 'opacity-100 translate-y-0'
          : 'opacity-0 translate-y-3 pointer-events-none'"
        class="absolute bottom-6 right-6 z-20 flex items-center gap-1.5 rounded-2xl bg-black/70 backdrop-blur-md border border-white/10 px-3 py-1.5 shadow-2xl transition-all duration-300 select-none text-white/80"
        @click.stop
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
      >
        <!-- Rotate Clockwise 90° -->
        <button
          type="button"
          @click="rotateClockwise"
          class="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-white/10 active:scale-95 transition-all text-white/70 hover:text-white cursor-pointer"
          :title="`顺时针旋转 90° (当前: ${rotation}°)`"
        >
          <RotateCw :size="15" />
        </button>

        <div class="h-4 w-px bg-white/10 mx-0.5"></div>

        <!-- Zoom Out -->
        <button
          type="button"
          @click="zoomOut()"
          :disabled="zoomScale <= 1"
          class="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-white/10 active:scale-95 disabled:opacity-30 disabled:pointer-events-none transition-all cursor-pointer"
          title="缩小 (Ctrl + 滚轮向下 / 快捷键: -)"
        >
          <ZoomOut :size="15" />
        </button>

        <!-- Current Zoom Percentage -->
        <button
          type="button"
          @click="resetAll"
          class="px-2 py-1 rounded-lg text-xs font-mono font-bold hover:bg-white/10 hover:text-white transition-all cursor-pointer"
          :class="isZoomed ? 'text-accent' : 'text-white/60'"
          title="重置缩放与旋转 (快捷键: 0)"
        >
          {{ zoomPercent }}%
        </button>

        <!-- Zoom In -->
        <button
          type="button"
          @click="zoomIn()"
          :disabled="zoomScale >= 5"
          class="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-white/10 active:scale-95 disabled:opacity-30 disabled:pointer-events-none transition-all cursor-pointer"
          title="放大 (Ctrl + 滚轮向上 / 快捷键: +)"
        >
          <ZoomIn :size="15" />
        </button>

        <!-- 1:1 Pixel Toggle -->
        <button
          type="button"
          @click="toggleActualSize"
          class="px-2 py-1 rounded-lg text-xs font-mono font-bold hover:bg-white/10 hover:text-white transition-all cursor-pointer ml-0.5"
          :class="isActualSize ? 'text-accent bg-accent/20' : 'text-white/60'"
          :title="isActualSize ? '适应屏幕 (快捷键: 0)' : '按 1:1 原图像素显示'"
        >
          1:1
        </button>

        <!-- Reset Button if Zoomed or Rotated -->
        <button
          v-if="isZoomed || rotation !== 0"
          type="button"
          @click="resetAll"
          class="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-white/10 text-white/60 hover:text-white transition-all cursor-pointer ml-0.5"
          title="适应屏幕 (快捷键: 0)"
        >
          <RotateCcw :size="14" />
        </button>
      </div>
    </div>
  </div>
</template>
