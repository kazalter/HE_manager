<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, Loader2, RotateCcw, RotateCw, ZoomIn, ZoomOut } from 'lucide-vue-next'
import type { Media } from '../../types'
import { useZoomScroller } from '../../composables/useZoomScroller'

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
const imageContentRef = ref<HTMLDivElement | null>(null)
const naturalSize = ref<[number, number] | null>(null)
const viewSize = ref<[number, number]>([0, 0])
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

// The image box fitted to the viewport for the current rotation; zooming multiplies it by --he-zoom.
const fitted = computed(() => {
  const [viewWidth, viewHeight] = viewSize.value
  const natural = naturalSize.value
  if (!natural || !viewWidth || !viewHeight) return null
  const [width, height] = rotation.value % 180 ? [natural[1], natural[0]] : natural
  const fit = Math.min(viewWidth / width, viewHeight / height)
  return { fit, box: [width * fit, height * fit], image: [natural[0] * fit, natural[1] * fit] }
})
const zoom = useZoomScroller({
  scroller: imageContainerRef, content: imageContentRef, centered: true,
  applyScale: (content, scale) => content.style.setProperty('--he-zoom', String(scale)),
  // 1:1 pixels can lie beyond the usual limit for a small fitted image.
  maxScale: () => Math.max(5, fitted.value ? 1 / fitted.value.fit : 1),
  doubleTapScale: () => 2.5,
  onSwipe: direction => { if (direction === 1) emit('next'); else emit('previous') },
})
const { isZoomed, zoomPercent, zoomIn, zoomOut } = zoom
const resetZoom = (animated = false) => zoom.reset(animated)
let resizeObserver: ResizeObserver | undefined
const measureView = () => {
  const container = imageContainerRef.value
  if (container) viewSize.value = [container.clientWidth, container.clientHeight]
}

const rotateClockwise = () => {
  resetZoom()
  rotation.value = (rotation.value + 90) % 360
}

const resetAll = () => {
  resetZoom()
  rotation.value = 0
  isActualSize.value = false
}

const onImageLoad = () => {
  const image = imgRef.value
  if (image?.naturalWidth && image.naturalHeight) naturalSize.value = [image.naturalWidth, image.naturalHeight]
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
    resetZoom(true)
    isActualSize.value = false
    return
  }
  // One image pixel per CSS pixel is the inverse of the fit.
  zoom.zoomTo(fitted.value ? 1 / fitted.value.fit : 2)
  isActualSize.value = true
}

const onWheel = (event: WheelEvent) => {
  if (props.wheelBehavior === 'zoom') {
    if ((event.target as HTMLElement | null)?.closest('.image-viewer-toolbar')) return
    zoom.handleWheelZoom(event)
    return
  }
  if (event.ctrlKey || event.metaKey) {
    zoom.handleWheelZoom(event)
    return
  }
  // Scrolling pans a zoomed image natively.
  if (isZoomed.value) return
  const now = Date.now()
  if (now - lastWheelAt < 320) return
  const delta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX
  if (Math.abs(delta) < 8) return
  event.preventDefault()
  lastWheelAt = now
  delta > 0 ? emit('next') : emit('previous')
}

const onViewerClick = () => {
  if (zoom.wasGesture()) return
  emit('viewerClick')
}
// A touch double-tap zooms; only a mouse double-click is passed on.
const onViewerDoubleClick = () => {
  if (zoom.wasDoubleTap()) return
  emit('viewerDoubleClick')
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
  naturalSize.value = null
  scheduleLoadingCheck(newUrl)
})

watch(isZoomed, (val) => {
  if (!val) {
    isActualSize.value = false
  }
})

onMounted(() => {
  scheduleLoadingCheck(props.imageUrl)
  measureView()
  if (imageContainerRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(measureView)
    resizeObserver.observe(imageContainerRef.value)
  }
  // A cached image can finish loading before the load listener is attached.
  if (imgRef.value?.complete) onImageLoad()
})

onBeforeUnmount(() => {
  clearLoadingTimer()
  resizeObserver?.disconnect()
})
</script>

<template>
  <div
    class="flex-1 min-h-0 flex flex-col items-center bg-black overflow-hidden relative group"
    @wheel="onWheel"
    @click="onViewerClick"
    @dblclick="onViewerDoubleClick"
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

      <!-- Main Image Container: a native scroller, so a zoomed image pans and glides natively. -->
      <div
        ref="imageContainerRef"
        class="he-image-scroller w-full h-full overflow-hidden select-none"
        style="overscroll-behavior: contain; touch-action: pan-x pan-y; scroll-axis-lock: none; scrollbar-width: none"
        :style="{ cursor: isZoomed ? (zoom.isDragging.value ? 'grabbing' : 'grab') : 'default' }"
        @mousedown="zoom.onMouseDown"
        @touchstart.passive="zoom.onTouchStart" @touchmove.passive="zoom.onTouchMove"
        @touchend.passive="zoom.onTouchEnd" @touchcancel.passive="zoom.onTouchEnd"
        @gesturestart="zoom.onGesture" @gesturechange="zoom.onGesture"
      >
        <!-- Centred while it fits, scrollable once zoomed past the viewport. -->
        <div class="grid min-h-full min-w-full place-items-center" style="width: max-content">
          <div
            ref="imageContentRef"
            class="relative"
            :style="fitted
              ? { width: `calc(${fitted.box[0]}px * var(--he-zoom, 1))`, height: `calc(${fitted.box[1]}px * var(--he-zoom, 1))` }
              : { width: `${viewSize[0]}px`, height: `${viewSize[1]}px` }"
          >
            <img
              ref="imgRef"
              :src="imageUrl"
              @load="onImageLoad"
              @error="onImageError"
              draggable="false"
              class="absolute left-1/2 top-1/2 max-w-none pointer-events-none select-none"
              :class="fitted ? '' : 'h-full w-full object-contain'"
              :style="{
                ...(fitted ? { width: `calc(${fitted.image[0]}px * var(--he-zoom, 1))`, height: `calc(${fitted.image[1]}px * var(--he-zoom, 1))` } : {}),
                transform: `translate(-50%, -50%) rotate(${rotation}deg)`,
              }"
              :alt="media.title"
            />
          </div>
        </div>
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
          :disabled="!isZoomed"
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
          :disabled="zoomPercent >= 500"
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
/* Older WebKit ignores scrollbar-width; a zoomed image pans by touch, drag and wheel. */
.he-image-scroller::-webkit-scrollbar {
  display: none;
}
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
