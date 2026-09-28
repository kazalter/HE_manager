<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, Download, ExternalLink, Image as ImageIcon, Maximize2, Minimize2, Pause, Play, X } from 'lucide-vue-next'
import ImageViewer from '../../media-detail/ImageViewer.vue'
import type { PawchiveAttachment, PawchivePost } from '../../../types/pawchive'
import { pawchiveMediaUrl } from '../../../utils/pawchiveApi'

const props = defineProps<{
  post: PawchivePost
  attachment: PawchiveAttachment
  attachmentIndex: number
  attachmentTotal: number
  attachments: PawchiveAttachment[]
  scopeLabel: string
  busy: boolean
  error: string
  hasPrevious: boolean
  ended: boolean
  autoplay: boolean
  interval: number
  downloadBusy: boolean
  downloadMessage: string
  downloadError: boolean
}>()
const emit = defineEmits<{
  close: []
  next: []
  previous: []
  selectAttachment: [index: number]
  'update:autoplay': [value: boolean]
  'update:interval': [value: number]
  playbackError: [message: string]
  downloadCurrent: []
  downloadPost: []
}>()
const viewerRef = ref<HTMLDivElement | null>(null)
const closeRef = ref<HTMLButtonElement | null>(null)
const isFullscreen = ref(false)
const controlsVisible = ref(true)
let controlsTimer: number | undefined
const videoRef = ref<HTMLVideoElement | null>(null)
const imageReady = ref(false)
const thumbnailStripRef = ref<HTMLDivElement | null>(null)
const failedPreviewKeys = ref(new Set<string>())
let imageTimer: number | undefined
let wheelGestureTimer: number | undefined
let wheelGestureUsed = false
let wheelDelta = 0

const resetWheelGesture = () => {
  window.clearTimeout(wheelGestureTimer)
  wheelGestureTimer = undefined
  wheelGestureUsed = false
  wheelDelta = 0
}
const onMediaWheel = (event: WheelEvent) => {
  if (props.attachment.media_type !== 'image' || event.ctrlKey || event.metaKey) return
  event.preventDefault()
  event.stopPropagation()
  if ((event.target as HTMLElement | null)?.closest('button, .image-viewer-toolbar')) return
  const rawDelta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX
  if (!rawDelta) return
  wheelDelta += rawDelta * (event.deltaMode === WheelEvent.DOM_DELTA_LINE ? 16 : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? window.innerHeight : 1)
  window.clearTimeout(wheelGestureTimer)
  wheelGestureTimer = window.setTimeout(resetWheelGesture, 350)
  if (wheelGestureUsed || props.busy || Math.abs(wheelDelta) < 8) return
  wheelGestureUsed = true
  wheelDelta > 0 ? emit('next') : emit('previous')
  wheelDelta = 0
}
const markPreviewFailed = (key: string) => {
  failedPreviewKeys.value = new Set(failedPreviewKeys.value).add(key)
}
const scrollActiveThumbnail = () => {
  void nextTick(() => {
    const strip = thumbnailStripRef.value
    const active = strip?.querySelector<HTMLButtonElement>('[aria-current="true"]')
    if (!strip || !active) return
    const stripRect = strip.getBoundingClientRect()
    const activeRect = active.getBoundingClientRect()
    strip.scrollTo({
      left: strip.scrollLeft + activeRect.left - stripRect.left - (stripRect.width - activeRect.width) / 2,
      behavior: 'smooth',
    })
  })
}
const selectAttachment = (index: number) => {
  if (props.busy || index === props.attachmentIndex) return
  emit('selectAttachment', index)
  scheduleControlsAutoHide()
}

const clearTimer = () => { window.clearTimeout(imageTimer); imageTimer = undefined }
const scheduleImage = () => {
  clearTimer()
  if (props.autoplay && props.attachment.media_type === 'image' && imageReady.value && !document.hidden && !props.busy) {
    imageTimer = window.setTimeout(() => emit('next'), props.interval * 1000)
  }
}
const startVideo = async () => {
  if (!props.autoplay || props.attachment.media_type !== 'video') return
  await nextTick()
  try { await videoRef.value?.play() }
  catch { emit('playbackError', '浏览器阻止自动播放，请点击视频继续播放。') }
}
const onImageLoaded = () => { imageReady.value = true; scheduleImage() }
const onImageError = () => { clearTimer(); emit('playbackError', '图片加载失败，可手动跳到下一项。') }
const onVideoEnded = () => { if (props.autoplay) emit('next') }
const onVideoPaused = () => {
  if (props.autoplay && !document.hidden && videoRef.value && !videoRef.value.ended) emit('update:autoplay', false)
}
const onVisibility = () => {
  if (document.hidden) { clearTimer(); videoRef.value?.pause() }
  else { scheduleImage(); void startVideo() }
}
const clearControlsTimer = () => { window.clearTimeout(controlsTimer); controlsTimer = undefined }
const scheduleControlsAutoHide = () => {
  clearControlsTimer()
  if (!isFullscreen.value || !controlsVisible.value) return
  controlsTimer = window.setTimeout(() => { controlsVisible.value = false; controlsTimer = undefined }, 3000)
}
const toggleControls = () => {
  if (!isFullscreen.value) return
  controlsVisible.value = !controlsVisible.value
  if (controlsVisible.value) scheduleControlsAutoHide()
  else clearControlsTimer()
}
const onMediaSurfaceClick = () => toggleControls()
const syncFullscreen = () => {
  isFullscreen.value = document.fullscreenElement === viewerRef.value
  controlsVisible.value = true
  clearControlsTimer()
  scheduleControlsAutoHide()
}
const toggleFullscreen = async () => {
  try {
    if (document.fullscreenElement === viewerRef.value) await document.exitFullscreen()
    else await viewerRef.value?.requestFullscreen()
  } catch {
    emit('playbackError', '无法切换全屏，请检查浏览器是否允许全屏显示。')
  }
}
const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Tab') {
    const focusable = [...document.querySelectorAll<HTMLElement>('[role="dialog"] a[href], [role="dialog"] button:not([disabled]), [role="dialog"] input:not([disabled])')]
    if (!focusable.length) return
    if (event.shiftKey && document.activeElement === focusable[0]) { event.preventDefault(); focusable[focusable.length - 1]?.focus() }
    else if (!event.shiftKey && document.activeElement === focusable[focusable.length - 1]) { event.preventDefault(); focusable[0]?.focus() }
    return
  }
  const target = event.target as HTMLElement | null
  if (target?.closest('input, textarea, select, video, [contenteditable="true"]')) return
  if (event.key === 'Escape') {
    if (document.fullscreenElement === viewerRef.value) {
      event.preventDefault()
      void document.exitFullscreen()
      return
    }
    event.preventDefault()
    emit('close')
  }
  else if (event.key === 'ArrowRight') { event.preventDefault(); emit('next') }
  else if (event.key === 'ArrowLeft') { event.preventDefault(); emit('previous') }
}
watch(() => props.attachment.attachment_key, () => {
  clearTimer()
  imageReady.value = false
  void startVideo()
})
watch(() => [props.post.post_key, props.attachmentIndex], scrollActiveThumbnail, { immediate: true })
watch(() => props.post.post_key, () => { failedPreviewKeys.value = new Set() })
watch(() => [props.autoplay, props.interval, props.busy], () => { scheduleImage(); void startVideo() })
onMounted(() => {
  closeRef.value?.focus()
  document.addEventListener('visibilitychange', onVisibility)
  document.addEventListener('fullscreenchange', syncFullscreen)
  window.addEventListener('keydown', onKeydown)
  if (props.attachment.media_type === 'video') void startVideo()
})
onBeforeUnmount(() => {
  clearTimer()
  clearControlsTimer()
  resetWheelGesture()
  videoRef.value?.pause()
  document.removeEventListener('visibilitychange', onVisibility)
  document.removeEventListener('fullscreenchange', syncFullscreen)
  window.removeEventListener('keydown', onKeydown)
  if (document.fullscreenElement === viewerRef.value) void document.exitFullscreen()
})
</script>

<template>
  <div ref="viewerRef" role="dialog" aria-modal="true" :aria-label="`Pawchive 查看器：${post.title}`" :class="isFullscreen ? 'h-screen w-screen' : ''" class="fixed inset-0 z-[70] bg-black/95 text-white flex flex-col">
    <header :class="isFullscreen ? ['absolute inset-x-0 top-0 z-30 bg-gradient-to-b from-black/90 via-black/65 to-transparent border-b-0', controlsVisible ? 'translate-y-0 opacity-100' : '-translate-y-full opacity-0 pointer-events-none'] : ''" class="shrink-0 px-3 sm:px-5 py-3 border-b border-white/15 flex items-center gap-3 transition-[transform,opacity] duration-300">
      <button ref="closeRef" type="button" class="min-w-11 min-h-11 flex items-center justify-center rounded-xl hover:bg-white/10 cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" aria-label="返回列表" @click="emit('close')"><X :size="21" /></button>
      <div class="min-w-0 flex-1"><p class="text-xs text-white/55 truncate">{{ post.creator_name }} · {{ scopeLabel }}</p><h2 class="text-sm sm:text-base font-bold truncate">{{ post.title }}</h2></div>
      <a :href="post.source_url" target="_blank" rel="noopener noreferrer" class="min-h-11 px-3 rounded-xl border border-white/15 text-xs font-semibold flex items-center gap-2 hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent"><ExternalLink :size="15" />来源</a>
      <button type="button" class="min-w-11 min-h-11 flex items-center justify-center rounded-xl border border-white/15 hover:bg-white/10 cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" :aria-label="isFullscreen ? '退出全屏' : '进入全屏'" :title="isFullscreen ? '退出全屏' : '进入全屏'" :aria-pressed="isFullscreen" @click="toggleFullscreen"><Minimize2 v-if="isFullscreen" :size="18" aria-hidden="true" /><Maximize2 v-else :size="18" aria-hidden="true" /></button>
    </header>
    <div class="flex-1 min-h-0 relative flex" @wheel.capture="onMediaWheel">
      <ImageViewer v-if="attachment.media_type === 'image'" :key="attachment.attachment_key" :media="{ title: attachment.filename }" :image-url="pawchiveMediaUrl(attachment.stream_ref)" :show-controls="true" :click-only-controls="false" :controls-visible="!isFullscreen || controlsVisible" @viewer-click="onMediaSurfaceClick" @previous="emit('previous')" @next="emit('next')" @viewer-double-click="() => {}" @controls-hover="() => {}" @loaded="onImageLoaded" @load-error="onImageError" />
      <div v-else class="w-full h-full flex items-center justify-center bg-black">
        <video ref="videoRef" :key="attachment.attachment_key" :src="pawchiveMediaUrl(attachment.stream_ref)" controls playsinline preload="metadata" class="w-full h-full object-contain" @click="onMediaSurfaceClick" @ended="onVideoEnded" @pause="onVideoPaused" @error="emit('playbackError', '视频无法播放，请尝试来源页面或下一项。')" />
      </div>
      <div v-if="busy" role="status" class="absolute inset-0 bg-black/65 flex items-center justify-center text-sm">正在查找下一项…</div>
    </div>
    <footer :class="isFullscreen ? ['absolute inset-x-0 bottom-0 z-30 bg-gradient-to-t from-black/90 via-black/65 to-transparent border-t-0', controlsVisible ? 'translate-y-0 opacity-100' : 'translate-y-full opacity-0 pointer-events-none'] : ''" class="shrink-0 border-t border-white/15 px-3 sm:px-5 py-3 space-y-2 transition-[transform,opacity] duration-300">
      <nav v-if="attachments.length > 1" aria-label="本帖媒体预览" class="border-b border-white/10 pb-2">
        <div class="mb-2 flex items-center justify-between gap-3 text-xs text-white/70">
          <span class="font-semibold">本帖媒体</span>
          <span>{{ attachmentIndex + 1 }} / {{ attachments.length }}</span>
        </div>
        <div ref="thumbnailStripRef" class="flex gap-2 overflow-x-auto pb-2 custom-scrollbar" @wheel.stop>
          <button
            v-for="(item, index) in attachments"
            :key="item.attachment_key"
            type="button"
            :disabled="busy"
            :aria-current="index === attachmentIndex ? 'true' : undefined"
            :aria-label="`查看本帖第 ${index + 1} 个媒体：${item.filename}`"
            :title="item.filename"
            :class="index === attachmentIndex ? 'border-accent ring-2 ring-accent/40' : 'border-white/15 hover:border-white/45'"
            class="relative h-16 w-16 shrink-0 overflow-hidden rounded-xl border-2 bg-white/5 transition-colors sm:h-20 sm:w-20 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white cursor-pointer"
            @click="selectAttachment(index)"
          >
            <img v-if="item.preview_ref && !failedPreviewKeys.has(item.attachment_key)" :src="pawchiveMediaUrl(item.preview_ref)" alt="" loading="lazy" decoding="async" draggable="false" class="h-full w-full object-cover" @error="markPreviewFailed(item.attachment_key)" />
            <span v-else class="flex h-full w-full items-center justify-center text-white/50"><ImageIcon :size="24" aria-hidden="true" /></span>
            <span v-if="item.media_type === 'video'" class="absolute inset-0 flex items-center justify-center bg-black/35"><Play :size="22" fill="currentColor" aria-hidden="true" /></span>
            <span class="absolute bottom-1 right-1 rounded bg-black/75 px-1 text-[10px] font-bold text-white">{{ index + 1 }}</span>
          </button>
        </div>
      </nav>
      <p v-if="error" role="alert" class="text-sm text-amber-300">{{ error }}</p>
      <p v-if="downloadMessage" :role="downloadError ? 'alert' : 'status'" :class="downloadError ? 'text-red-300' : 'text-emerald-300'" class="text-sm">{{ downloadMessage }}</p>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <p class="text-xs text-white/65">本帖可播放附件 {{ attachmentIndex + 1 }} / {{ attachmentTotal }}<span class="ml-2">· {{ attachment.filename }}</span></p>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" :disabled="downloadBusy" class="min-h-11 px-3 rounded-xl border border-white/15 flex items-center gap-1 text-sm disabled:opacity-50 cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" @click="emit('downloadCurrent')"><Download :size="15" />当前附件</button>
          <button type="button" :disabled="downloadBusy" class="min-h-11 px-3 rounded-xl border border-white/15 flex items-center gap-1 text-sm disabled:opacity-50 cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" @click="emit('downloadPost')">下载本帖</button>
          <label class="text-xs text-white/70 flex items-center gap-2">图片间隔
            <input type="number" min="1" max="300" :value="interval" class="w-16 min-h-11 rounded-lg bg-white/10 border border-white/15 px-2 text-white" @change="emit('update:interval', Math.min(300, Math.max(1, Number(($event.target as HTMLInputElement).value) || 5)))" />秒
          </label>
          <button type="button" class="min-h-11 px-3 rounded-xl border border-white/15 flex items-center gap-2 text-sm cursor-pointer hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent" :aria-pressed="autoplay" @click="emit('update:autoplay', !autoplay)"><Pause v-if="autoplay" :size="16" /><Play v-else :size="16" />{{ autoplay ? '暂停连播' : '自动连播' }}</button>
          <button type="button" :disabled="!hasPrevious || busy" class="min-h-11 px-3 rounded-xl border border-white/15 flex items-center gap-1 text-sm disabled:opacity-40 cursor-pointer hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent" @click="emit('previous')"><ArrowLeft :size="16" />上一项</button>
          <button type="button" :disabled="ended || busy" class="min-h-11 px-3 rounded-xl bg-accent flex items-center gap-1 text-sm font-bold disabled:opacity-40 cursor-pointer focus-visible:ring-2 focus-visible:ring-white" @click="emit('next')">{{ ended ? '范围末尾' : '下一项' }}<ArrowRight :size="16" /></button>
        </div>
      </div>
    </footer>
  </div>
</template>
