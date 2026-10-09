<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, Loader2, RotateCcw, RotateCw, ZoomIn, ZoomOut } from 'lucide-vue-next'
import type { Media } from '../../types'
import { useImageViewerZoom } from '../../composables/useImageViewerZoom'

const props = withDefaults(defineProps<{
  media: Pick<Media, 'title'>
  imageUrl: string
  showControls: boolean
  clickOnlyControls: boolean
  controlsVisible?: boolean
  wheelBehavior?: 'navigate' | 'zoom'
}>(), {
  wheelBehavior: 'navigate',
})

const emit = defineEmits<{
  previous: []
  next: []
  viewerClick: []
  viewerDoubleClick: []
  controlsHover: [hovering: boolean]
  loaded: []
  loadError: []
}>()

const imgRef = ref<HTMLImageElement | null>(null)
const imageContainerRef = ref<HTMLDivElement | null>(null)
const showLoading = ref(false)
const rotation = ref(0)
const isActualSize = ref(false)
let lastWheelAt = 0
let loadingTimer: number | undefined

const clearLoadingTimer = () => {
  if (loadingTimer) {
    window.clearTimeout(loadingTimer)
    loadingTimer = undefined
  }
}

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
  onTouchStart, onTouchMove, onTouchEnd, wasTouchGesture,
} = useImageViewerZoom(imageContainerRef, { onSwipe: direction => { if (direction === 1) emit('next'); else emit('previous') } })

const rotateClockwise = () => {
  rotation.value = (rotation.value + 90) % 360
}

const resetAll = () => {
  resetZoom()
  rotation.value = 0
  isActualSize.value = false
}

const onImageLoad = () => {
  clearLoadingTimer()
  showLoading.value = false
  emit('loaded')
}

const onImageError = () => {
  clearLoadingTimer()
  showLoading.value = false
  emit('loadError')
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
  if (props.wheelBehavior === 'zoom') {
    if ((event.target as HTMLElement | null)?.closest('.image-viewer-toolbar')) return
    handleZoomWheel(event)
    return
  }
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
  if (wasZoomDragging() || wasTouchGesture()) return
  emit('viewerClick')
}

const scheduleLoadingCheck = (url: string) => {
  clearLoadingTimer()
  if (typeof Image !== 'undefined') {
    const probe = new Image()
    probe.src = url
    if (probe.complete) {
      showLoading.value = false
      return
    }
  }
  // Only display loading indicator if the image takes > 250ms (prevents flicker on LAN/cached images)
  loadingTimer = window.setTimeout(() => {
    showLoading.value = true
  }, 250)
}

watch(() => props.imageUrl, (newUrl) => {
  resetAll()
  scheduleLoadingCheck(newUrl)
})

watch(isZoomed, (val) => {
  if (!val) {
    isActualSize.value = false
  }
})

onMounted(() => {
  scheduleLoadingCheck(props.imageUrl)
})

onBeforeUnmount(() => {
  clearLoadingTimer()
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
      <!-- Non-blocking Loading Indicator (shown only if loading exceeds 250ms) -->
      <Transition
        enter-active-class="transition-opacity duration-200"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition-opacity duration-200"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="showLoading"
          class="pointer-events-none absolute left-1/2 top-6 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full bg-black/75 px-4 py-2 text-white/85 ring-1 ring-inset ring-white/10"
        >
          <Loader2 class="size-4 animate-spin" aria-hidden="true" />
          <span class="text-meta">加载中…</span>
        </div>
      </Transition>

      <!-- Left Prev Button -->
      <button
        @click.stop="emit('previous')"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        :class="controlsVisible !== undefined
          ? (controlsVisible ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-6 pointer-events-none')
          : (showControls
            ? 'opacity-100 translate-x-0'
            : clickOnlyControls
              ? 'opacity-0 -translate-x-6 pointer-events-none'
              : 'opacity-0 -translate-x-6 hover:opacity-100 hover:translate-x-0')"
        class="he-page-nav absolute left-5 z-20 grid size-12 place-items-center rounded-full bg-black/60 text-white/80 transition-[opacity,transform,background-color,color] duration-200 ease-out hover:bg-black/80 hover:text-white focus-ring"
        title="上一项" aria-label="上一项"
      >
        <ChevronLeft :size="26" aria-hidden="true" />
      </button>

      <!-- Main Image Container -->
      <div
        ref="imageContainerRef"
        class="w-full h-full flex items-center justify-center overflow-hidden select-none"
        :style="{ cursor: isZoomed ? (isZoomPanning ? 'grabbing' : 'grab') : 'default' }"
        @mousedown="onZoomMouseDown"
        @touchstart="onTouchStart" @touchmove="onTouchMove" @touchend="onTouchEnd" @touchcancel="onTouchEnd"
        style="touch-action: none"
      >
        <img
          ref="imgRef"
          :src="imageUrl"
          @load="onImageLoad"
          @error="onImageError"
          class="h-full w-full object-contain pointer-events-none select-none"
          :style="{
            transform: `translate3d(${zoomTx}px, ${zoomTy}px, 0px) scale(${zoomScale}) rotate(${rotation}deg)`,
            transition: isZoomPanning ? 'none' : 'transform 0.15s ease-out',
          }"
          :alt="media.title"
        />
      </div>

      <!-- Right Next Button -->
      <button
        @click.stop="emit('next')"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        :class="controlsVisible !== undefined
          ? (controlsVisible ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-6 pointer-events-none')
          : (showControls
            ? 'opacity-100 translate-x-0'
            : clickOnlyControls
              ? 'opacity-0 translate-x-6 pointer-events-none'
              : 'opacity-0 translate-x-6 hover:opacity-100 hover:translate-x-0')"
        class="he-page-nav absolute right-5 z-20 grid size-12 place-items-center rounded-full bg-black/60 text-white/80 transition-[opacity,transform,background-color,color] duration-200 ease-out hover:bg-black/80 hover:text-white focus-ring"
        title="下一项" aria-label="下一项"
      >
        <ChevronRight :size="26" aria-hidden="true" />
      </button>

      <!-- Floating Toolbar Pill -->
      <div
        :class="(controlsVisible === undefined ? showControls || isZoomed || rotation !== 0 : controlsVisible)
          ? 'opacity-100 translate-y-0'
          : 'opacity-0 translate-y-3 pointer-events-none'"
        class="image-viewer-toolbar absolute bottom-6 right-6 z-20 flex select-none items-center gap-0.5 rounded-2xl bg-black/75 p-1 text-white/80 ring-1 ring-inset ring-white/10 transition-[opacity,transform] duration-200 ease-out"
        @click.stop
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
      >
        <!-- Rotate Clockwise 90° -->
        <button
          type="button"
          @click="rotateClockwise"
          class="he-viewer-btn w-8 hover:bg-white/10 hover:text-white text-white/75"
          aria-label="顺时针旋转 90°"
          :title="`顺时针旋转 90° (当前: ${rotation}°)`"
        >
          <RotateCw :size="16" aria-hidden="true" />
        </button>

        <div class="mx-0.5 h-5 w-px bg-white/15" aria-hidden="true"></div>

        <!-- Zoom Out -->
        <button
          type="button"
          @click="zoomOut()"
          :disabled="zoomScale <= 1"
          class="he-viewer-btn w-8 hover:bg-white/10 hover:text-white disabled:pointer-events-none disabled:opacity-35"
          :title="wheelBehavior === 'zoom' ? '缩小 (滚轮向下 / 快捷键: -)' : '缩小 (Ctrl + 滚轮向下 / 快捷键: -)'"
        >
          <ZoomOut :size="16" aria-hidden="true" />
        </button>

        <!-- Current Zoom Percentage -->
        <button
          type="button"
          @click="resetAll"
          class="he-viewer-btn min-w-14 px-2 text-meta font-medium tabular-nums hover:bg-white/10 hover:text-white"
          :class="isZoomed ? 'text-white' : 'text-white/65'"
          title="重置缩放与旋转 (快捷键: 0)"
        >
          {{ zoomPercent }}%
        </button>

        <!-- Zoom In -->
        <button
          type="button"
          @click="zoomIn()"
          :disabled="zoomScale >= 5"
          class="he-viewer-btn w-8 hover:bg-white/10 hover:text-white disabled:pointer-events-none disabled:opacity-35"
          :title="wheelBehavior === 'zoom' ? '放大 (滚轮向上 / 快捷键: +)' : '放大 (Ctrl + 滚轮向上 / 快捷键: +)'"
        >
          <ZoomIn :size="16" aria-hidden="true" />
        </button>

        <!-- 1:1 Pixel Toggle -->
        <button
          type="button"
          @click="toggleActualSize"
          class="he-viewer-btn px-2 text-meta font-medium tabular-nums hover:bg-white/10 hover:text-white"
          :class="isActualSize ? 'bg-white/15 text-white' : 'text-white/65'"
          :aria-pressed="isActualSize"
          :title="isActualSize ? '适应屏幕 (快捷键: 0)' : '按 1:1 原图像素显示'"
        >
          1:1
        </button>

        <!-- Reset Button if Zoomed or Rotated -->
        <button
          v-if="isZoomed || rotation !== 0"
          type="button"
          @click="resetAll"
          class="he-viewer-btn w-8 hover:bg-white/10 hover:text-white text-white/65"
          aria-label="适应屏幕"
          title="适应屏幕 (快捷键: 0)"
        >
          <RotateCcw :size="15" aria-hidden="true" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.he-viewer-btn {
  display: inline-flex;
  height: 32px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  transition: background-color 120ms var(--ease-out), color 120ms var(--ease-out);
}
@media (max-width: 899px) {
  .image-viewer-toolbar { left: 12px; right: 12px; bottom: calc(12px + env(safe-area-inset-bottom)); justify-content: center; gap: 2px; }
  .image-viewer-toolbar button { min-width: 44px; min-height: 44px; }
  .he-page-nav.left-5 { left: 8px; width: 44px; height: 44px; }
  .he-page-nav.right-5 { right: 8px; width: 44px; height: 44px; }
}
</style>
