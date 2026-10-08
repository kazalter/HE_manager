<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, Download, ExternalLink, Image as ImageIcon, ImageOff, Loader2, Maximize2, Minimize2, Pause, Play, RotateCw, X } from 'lucide-vue-next'
import ImageViewer from '../../media-detail/ImageViewer.vue'
import type { PawchiveAttachment, PawchivePost } from '../../../types/pawchive'
import { pawchiveMediaUrl } from '../../../utils/pawchiveApi'
import { fetchImageBlob, isAbortError } from '../../../utils/pawchiveImageLoader'

const props = defineProps<{
  post: PawchivePost
  attachment: PawchiveAttachment
  attachmentIndex: number
  attachmentTotal: number
  attachments: PawchiveAttachment[]
  nextPostKey?: string | null
  nextPostAttachments?: PawchiveAttachment[]
  scopeLabel: string
  busy: boolean
  error: string
  notice?: string
  skipped?: number
  /** Refetch the current post so an expired or stalled media ref is replaced. */
  reloadMedia?: () => Promise<boolean>
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
const nativeFullscreen = ref(false)
const fallbackFullscreen = ref(false)
const isFullscreen = computed(() => nativeFullscreen.value || fallbackFullscreen.value)
const controlsVisible = ref(true)
const controlsHovered = ref(false)
let controlsTimer: number | undefined
const videoRef = ref<HTMLVideoElement | null>(null)
const imageReady = ref(false)
const displayImageUrl = ref('')
const preloadedImageUrls = new Map<string, Map<string, string>>()
const attemptedImageKeys = new Map<string, Set<string>>()
let preloadController: AbortController | null = null
let preloadPending = false
let imageController: AbortController | null = null
// Fraction of the current original received, or null while the size is unknown.
const loadProgress = ref<number | null>(null)
const thumbnailNavRef = ref<HTMLElement | null>(null)
const thumbnailStripRef = ref<HTMLDivElement | null>(null)
const hoverPreviewIndex = ref(-1)
const hoverPreviewX = ref(0)
const hoverPreviewWidth = ref(200)
const failedPreviewKeys = ref(new Set<string>())
let imageTimer: number | undefined
// Bumps the media URL so a retry never reuses a stalled request for the same ref.
const retryNonce = ref(0)
const retriedKey = ref('')
const loadFailed = ref(false)
const showPlaceholder = ref(false)
const countdownKey = ref(0)
let placeholderTimer: number | undefined
let skipTimer: number | undefined
// Originals can be 20+ MB behind a slow proxy, so only a pause in received bytes counts as a stall.
const IMAGE_STALL_MS = 20_000
const withNonce = (url: string) => {
  if (!url || !retryNonce.value) return url
  return `${url}${url.includes('?') ? '&' : '?'}retry=${retryNonce.value}`
}
const videoUrl = computed(() => withNonce(pawchiveMediaUrl(props.attachment.stream_ref)))
const placeholderUrl = computed(() => props.attachment.media_type === 'image' && props.attachment.preview_ref &&
  !failedPreviewKeys.value.has(props.attachment.attachment_key) ? pawchiveMediaUrl(props.attachment.preview_ref) : '')
let wheelGestureTimer: number | undefined
let wheelGestureUsed = false
let wheelDelta = 0

const abortPostPreload = () => {
  preloadController?.abort()
  preloadController = null
  preloadPending = false
}
const releaseOtherPosts = (keep: Set<string>) => {
  for (const [postKey, images] of preloadedImageUrls) {
    if (keep.has(postKey)) continue
    for (const url of images.values()) URL.revokeObjectURL(url)
    preloadedImageUrls.delete(postKey)
  }
  for (const postKey of attemptedImageKeys.keys()) {
    if (!keep.has(postKey)) attemptedImageKeys.delete(postKey)
  }
}
const stopPostPreload = () => {
  abortPostPreload()
  releaseOtherPosts(new Set())
}
const cacheImage = (postKey: string, key: string, blob: Blob) => {
  const images = preloadedImageUrls.get(postKey) || new Map<string, string>()
  preloadedImageUrls.set(postKey, images)
  const existing = images.get(key)
  if (existing) return existing
  const url = URL.createObjectURL(blob)
  images.set(key, url)
  return url
}
const dropCachedImage = (postKey: string, key: string) => {
  const url = preloadedImageUrls.get(postKey)?.get(key)
  if (!url) return
  URL.revokeObjectURL(url)
  preloadedImageUrls.get(postKey)?.delete(key)
}
const abortImageLoad = () => {
  imageController?.abort()
  imageController = null
}
const loadCurrentImage = async () => {
  abortImageLoad()
  const item = props.attachment
  const postKey = props.post.post_key
  if (item.media_type !== 'image' || !item.stream_ref) {
    displayImageUrl.value = ''
    return
  }
  const ready = preloadedImageUrls.get(postKey)?.get(item.attachment_key)
  if (ready) {
    displayImageUrl.value = ready
    return
  }
  displayImageUrl.value = ''
  loadProgress.value = null
  const controller = new AbortController()
  imageController = controller
  try {
    const blob = await fetchImageBlob(withNonce(pawchiveMediaUrl(item.stream_ref)), {
      signal: controller.signal,
      idleMs: IMAGE_STALL_MS,
      onProgress: (progress) => { if (imageController === controller) loadProgress.value = progress },
    })
    if (imageController !== controller) return
    displayImageUrl.value = cacheImage(postKey, item.attachment_key, blob)
  } catch (error) {
    if (isAbortError(error) || imageController !== controller) return
    void onMediaFailed()
  } finally {
    if (imageController === controller) imageController = null
  }
}
const preloadImages = async (postKey: string, items: PawchiveAttachment[], controller: AbortController) => {
  const images = preloadedImageUrls.get(postKey) || new Map<string, string>()
  const attempted = attemptedImageKeys.get(postKey) || new Set<string>()
  preloadedImageUrls.set(postKey, images)
  attemptedImageKeys.set(postKey, attempted)
  for (const item of items) {
    if (controller.signal.aborted) return
    if (item.media_type !== 'image' || !item.stream_ref || images.has(item.attachment_key) || attempted.has(item.attachment_key)) continue
    try {
      const blob = await fetchImageBlob(pawchiveMediaUrl(item.stream_ref), { signal: controller.signal, idleMs: IMAGE_STALL_MS })
      if (controller.signal.aborted) return
      cacheImage(postKey, item.attachment_key, blob)
    } catch {
      if (controller.signal.aborted) return
    } finally {
      if (!controller.signal.aborted) attempted.add(item.attachment_key)
    }
  }
}
const preloadPostImages = () => {
  if (preloadController) return
  const controller = new AbortController()
  preloadController = controller
  const postKey = props.post.post_key
  const nextIndex = props.attachmentIndex + 1
  const ordered = [...props.attachments.slice(nextIndex), ...props.attachments.slice(0, nextIndex)]
  void (async () => {
    await preloadImages(postKey, ordered, controller)
    if (controller.signal.aborted) return
    const nextPostKey = props.nextPostKey
    if (nextPostKey && nextPostKey !== postKey) {
      await preloadImages(nextPostKey, props.nextPostAttachments || [], controller)
    }
  })().finally(() => {
    if (preloadController !== controller) return
    preloadController = null
    if (preloadPending) {
      preloadPending = false
      preloadPostImages()
    }
  })
}

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
const updateHoverPreviewPosition = () => {
  const nav = thumbnailNavRef.value
  const button = thumbnailStripRef.value?.children.item(hoverPreviewIndex.value) as HTMLElement | null
  if (!nav || !button || hoverPreviewIndex.value < 0) return
  const navRect = nav.getBoundingClientRect()
  const buttonRect = button.getBoundingClientRect()
  const width = Math.min(200, Math.max(0, navRect.width - 16))
  const center = buttonRect.left + buttonRect.width / 2 - navRect.left
  hoverPreviewWidth.value = width
  hoverPreviewX.value = Math.max(width / 2 + 8, Math.min(navRect.width - width / 2 - 8, center))
}
const showHoverPreview = (index: number) => {
  hoverPreviewIndex.value = index
  updateHoverPreviewPosition()
}
const hideHoverPreview = (index: number) => {
  if (hoverPreviewIndex.value === index) hoverPreviewIndex.value = -1
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

const clearTimer = () => { window.clearTimeout(imageTimer); imageTimer = undefined; countdownKey.value = 0 }
const scheduleImage = () => {
  clearTimer()
  if (props.autoplay && props.attachment.media_type === 'image' && imageReady.value && !document.hidden && !props.busy) {
    imageTimer = window.setTimeout(() => emit('next'), props.interval * 1000)
    countdownKey.value = Date.now()
  }
}
const clearLoadTimers = () => {
  window.clearTimeout(placeholderTimer)
  window.clearTimeout(skipTimer)
  placeholderTimer = skipTimer = undefined
}
const startLoadWatch = () => {
  clearLoadTimers()
  showPlaceholder.value = false
  if (props.attachment.media_type !== 'image') return
  // A short delay keeps the blurred thumbnail from flashing over cached images.
  placeholderTimer = window.setTimeout(() => { showPlaceholder.value = !imageReady.value }, 150)
}
const reloadCurrentMedia = async () => {
  const key = props.attachment.attachment_key
  await props.reloadMedia?.().catch(() => false)
  await nextTick()
  if (key !== props.attachment.attachment_key) return
  retryNonce.value++
  if (props.attachment.media_type === 'image') {
    startLoadWatch()
    void loadCurrentImage()
  } else {
    void startVideo()
  }
}
// First failure retries with a fresh ref; a second one skips (autoplay) or waits for the user.
const onMediaFailed = async () => {
  const key = props.attachment.attachment_key
  clearTimer()
  if (retriedKey.value !== key) {
    retriedKey.value = key
    await reloadCurrentMedia()
    return
  }
  loadFailed.value = true
  const kind = props.attachment.media_type === 'video' ? '视频' : '图片'
  if (props.autoplay && !props.ended) {
    emit('playbackError', `${kind}加载失败，即将跳到下一项。`)
    skipTimer = window.setTimeout(() => {
      if (key !== props.attachment.attachment_key || !props.autoplay) return
      emit('next')
      emit('playbackError', `上一个${kind}加载失败，已自动跳过。`)
    }, 2500)
  } else {
    emit('playbackError', `${kind}加载失败，可重试或跳到下一项。`)
  }
}
const retryMedia = () => {
  loadFailed.value = false
  emit('playbackError', '')
  void reloadCurrentMedia()
}
const startVideo = async () => {
  if (!props.autoplay || props.attachment.media_type !== 'video') return
  await nextTick()
  try { await videoRef.value?.play() }
  catch { emit('playbackError', '浏览器阻止自动播放，请点击视频继续播放。') }
}
const onImageLoaded = () => {
  imageReady.value = true
  loadFailed.value = false
  clearLoadTimers()
  scheduleImage()
  preloadPostImages()
}
const onImageError = () => {
  // A blob that fails to decode must not be served again by the retry.
  dropCachedImage(props.post.post_key, props.attachment.attachment_key)
  preloadPostImages()
  void onMediaFailed()
}
const onVideoEnded = () => { if (props.autoplay) emit('next') }
const onVideoPaused = () => {
  const video = videoRef.value
  // Reloading a source also fires `pause` before any data exists; only a user pause stops autoplay.
  if (!video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return
  if (props.autoplay && !document.hidden && !video.ended) emit('update:autoplay', false)
}
const onVisibility = () => {
  if (document.hidden) { clearTimer(); videoRef.value?.pause() }
  else { scheduleImage(); void startVideo() }
}
const clearControlsTimer = () => { window.clearTimeout(controlsTimer); controlsTimer = undefined }
const scheduleControlsAutoHide = () => {
  clearControlsTimer()
  if (!isFullscreen.value || !controlsVisible.value || controlsHovered.value) return
  controlsTimer = window.setTimeout(() => { controlsVisible.value = false; controlsTimer = undefined }, 3000)
}
const onControlsHover = (hovering: boolean) => {
  controlsHovered.value = hovering
  if (hovering) clearControlsTimer()
  else scheduleControlsAutoHide()
}
const toggleControls = () => {
  if (!isFullscreen.value) return
  controlsVisible.value = !controlsVisible.value
  if (controlsVisible.value) scheduleControlsAutoHide()
  else clearControlsTimer()
}
const onMediaSurfaceClick = () => toggleControls()
const resetFullscreenControls = () => {
  controlsVisible.value = true
  clearControlsTimer()
  scheduleControlsAutoHide()
}
const syncFullscreen = () => {
  nativeFullscreen.value = document.fullscreenElement === viewerRef.value
  resetFullscreenControls()
}
const toggleFullscreen = async () => {
  if (fallbackFullscreen.value) {
    fallbackFullscreen.value = false
    resetFullscreenControls()
    return
  }
  if (document.fullscreenElement === viewerRef.value) {
    try { await document.exitFullscreen() }
    catch { emit('playbackError', '无法退出全屏，请检查浏览器是否允许全屏显示。') }
    return
  }
  try {
    if (!viewerRef.value?.requestFullscreen) throw new Error('Fullscreen API unavailable')
    await viewerRef.value.requestFullscreen()
    // Some mobile browsers resolve without putting a non-video element fullscreen.
    if (document.fullscreenElement !== viewerRef.value) throw new Error('Fullscreen was not entered')
  } catch {
    if (props.attachment.media_type !== 'image') {
      emit('playbackError', '无法切换全屏，请检查浏览器是否允许全屏显示。')
      return
    }
    fallbackFullscreen.value = true
    resetFullscreenControls()
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
    if (isFullscreen.value) {
      event.preventDefault()
      void toggleFullscreen()
      return
    }
    event.preventDefault()
    emit('close')
  }
  else if (event.key === 'ArrowRight') { event.preventDefault(); emit('next') }
  else if (event.key === 'ArrowLeft') { event.preventDefault(); emit('previous') }
}
watch(() => props.post.post_key, () => {
  abortPostPreload()
  releaseOtherPosts(new Set([props.post.post_key]))
  if (props.attachment.media_type !== 'image') preloadPostImages()
}, { immediate: true })
watch(() => props.nextPostKey, (postKey) => {
  if (!postKey || postKey === props.post.post_key) return
  if (preloadController) preloadPending = true
  else if (props.attachment.media_type !== 'image' || imageReady.value) preloadPostImages()
})
watch(() => [props.post.post_key, props.attachment.attachment_key], () => {
  retryNonce.value = 0
  retriedKey.value = ''
  loadFailed.value = false
  clearTimer()
  imageReady.value = false
  startLoadWatch()
  void loadCurrentImage()
  if (props.attachment.media_type !== 'image') preloadPostImages()
  void startVideo()
})
watch(() => [props.post.post_key, props.attachmentIndex], scrollActiveThumbnail, { immediate: true })
watch(() => props.post.post_key, () => { failedPreviewKeys.value = new Set(); hoverPreviewIndex.value = -1 })
watch(() => [props.autoplay, props.interval, props.busy], () => { scheduleImage(); void startVideo() })
onMounted(() => {
  startLoadWatch()
  void loadCurrentImage()
  closeRef.value?.focus()
  document.addEventListener('visibilitychange', onVisibility)
  document.addEventListener('fullscreenchange', syncFullscreen)
  window.addEventListener('keydown', onKeydown)
  if (props.attachment.media_type === 'video') void startVideo()
})
onBeforeUnmount(() => {
  abortImageLoad()
  stopPostPreload()
  clearTimer()
  clearLoadTimers()
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
  <div ref="viewerRef" role="dialog" aria-modal="true" :aria-label="`Pawchive 查看器：${post.title}`" :class="nativeFullscreen ? 'h-screen w-screen' : ''" class="he-pawchive-viewer fixed inset-0 z-[70] bg-black/95 text-white flex flex-col">
    <header :class="isFullscreen ? ['absolute inset-x-0 top-0 z-30 bg-gradient-to-b from-black/90 via-black/65 to-transparent border-b-0', controlsVisible ? 'translate-y-0 opacity-100' : '-translate-y-full opacity-0 pointer-events-none'] : ''" class="shrink-0 px-3 sm:px-5 py-3 border-b border-white/15 flex items-center gap-3 transition-[transform,opacity] duration-300" @mouseenter="onControlsHover(true)" @mouseleave="onControlsHover(false)">
      <button ref="closeRef" type="button" class="min-w-11 min-h-11 flex items-center justify-center rounded-xl hover:bg-white/10 cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" aria-label="返回列表" @click="emit('close')"><X :size="21" /></button>
      <div class="min-w-0 flex-1"><p class="text-xs text-white/55 truncate">{{ post.creator_name }} · {{ scopeLabel }}</p><h2 class="text-sm sm:text-base font-bold truncate">{{ post.title }}</h2></div>
      <a :href="post.source_url" target="_blank" rel="noopener noreferrer" class="min-h-11 px-3 rounded-xl border border-white/15 text-xs font-semibold flex items-center gap-2 hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent"><ExternalLink :size="15" />来源</a>
      <button
        v-if="attachment.media_type === 'image'"
        type="button"
        :disabled="downloadBusy || busy || !attachment.stream_ref"
        class="min-w-11 min-h-11 px-2 sm:px-3 flex items-center justify-center gap-2 rounded-xl border border-white/15 text-xs sm:text-sm font-semibold hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        aria-label="下载当前图片到媒体库"
        title="下载当前图片到媒体库"
        @click="emit('downloadCurrent')"
      ><Download :size="17" aria-hidden="true" /><span class="hidden sm:inline">{{ downloadBusy ? '正在核对…' : '下载此图' }}</span></button>
      <button type="button" class="min-w-11 min-h-11 flex items-center justify-center rounded-xl border border-white/15 hover:bg-white/10 cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" :aria-label="isFullscreen ? '退出全屏' : '进入全屏'" :title="isFullscreen ? '退出全屏' : '进入全屏'" :aria-pressed="isFullscreen" @click="toggleFullscreen"><Minimize2 v-if="isFullscreen" :size="18" aria-hidden="true" /><Maximize2 v-else :size="18" aria-hidden="true" /></button>
    </header>
    <div class="flex-1 min-h-0 relative flex" @wheel.capture="onMediaWheel">
      <img v-if="placeholderUrl && showPlaceholder && !imageReady && !loadFailed" :src="placeholderUrl" alt="" aria-hidden="true" draggable="false" class="pointer-events-none absolute inset-0 z-10 h-full w-full scale-105 object-contain opacity-60 blur-md" />
      <div v-if="attachment.media_type === 'image' && !displayImageUrl && showPlaceholder && !loadFailed" role="status" class="pointer-events-none absolute bottom-4 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/15 bg-black/75 px-4 py-2 text-sm shadow-xl backdrop-blur-md">
        <Loader2 :size="16" class="shrink-0 animate-spin text-accent" aria-hidden="true" />
        <span>正在加载原图<template v-if="loadProgress !== null"> {{ Math.round(loadProgress * 100) }}%</template></span>
      </div>
      <ImageViewer v-if="attachment.media_type === 'image' && displayImageUrl" :key="attachment.attachment_key" :media="{ title: attachment.filename }" :image-url="displayImageUrl" :show-controls="true" :click-only-controls="false" :controls-visible="!isFullscreen || controlsVisible" @viewer-click="onMediaSurfaceClick" @previous="emit('previous')" @next="emit('next')" @viewer-double-click="() => {}" @controls-hover="onControlsHover" @loaded="onImageLoaded" @load-error="onImageError" />
      <div v-else-if="attachment.media_type !== 'image'" class="w-full h-full flex items-center justify-center bg-black">
        <video ref="videoRef" :key="attachment.attachment_key" :src="videoUrl" controls playsinline preload="metadata" class="w-full h-full object-contain" @click="onMediaSurfaceClick" @ended="onVideoEnded" @pause="onVideoPaused" @loadeddata="loadFailed = false" @error="onMediaFailed" />
      </div>
      <div v-if="loadFailed" class="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-black px-6 text-center">
        <ImageOff :size="40" class="text-white/40" aria-hidden="true" />
        <p class="text-sm text-white/75">{{ attachment.media_type === 'video' ? '视频' : '图片' }}暂时无法加载</p>
        <div class="flex gap-2">
          <button type="button" class="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/20 px-4 text-sm hover:bg-white/10 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" @click="retryMedia"><RotateCw :size="15" aria-hidden="true" />重试</button>
          <button type="button" :disabled="ended || busy" class="inline-flex min-h-11 items-center gap-2 rounded-xl bg-accent px-4 text-sm font-bold disabled:opacity-40 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white" @click="emit('next')">下一项<ArrowRight :size="15" aria-hidden="true" /></button>
        </div>
      </div>
      <div v-if="busy" role="status" :class="isFullscreen && controlsVisible ? 'top-20' : 'top-4'" class="pointer-events-none absolute left-1/2 z-30 flex max-w-[calc(100%-2rem)] -translate-x-1/2 items-center gap-2 rounded-full border border-white/15 bg-black/75 px-4 py-2 text-sm shadow-xl backdrop-blur-md">
        <Loader2 :size="16" class="shrink-0 animate-spin text-accent" aria-hidden="true" />
        <span class="truncate">正在查找下一篇有媒体的帖子<template v-if="skipped"> · 已跳过 {{ skipped }} 篇</template></span>
      </div>
      <div v-if="countdownKey" :key="countdownKey" aria-hidden="true" class="pawchive-countdown pointer-events-none absolute bottom-0 left-0 z-20 h-0.5 bg-accent/80" :style="{ animationDuration: `${interval}s` }"></div>
    </div>
    <footer :class="isFullscreen ? ['absolute inset-x-0 bottom-0 z-30 bg-gradient-to-t from-black/90 via-black/65 to-transparent border-t-0', controlsVisible ? 'translate-y-0 opacity-100' : 'translate-y-full opacity-0 pointer-events-none'] : ''" class="shrink-0 border-t border-white/15 px-3 sm:px-5 py-3 space-y-2 transition-[transform,opacity] duration-300" @mouseenter="onControlsHover(true)" @mouseleave="onControlsHover(false)">
      <nav v-if="attachments.length > 1" ref="thumbnailNavRef" aria-label="本帖媒体预览" class="relative border-b border-white/10 pb-2">
        <div class="mb-2 flex items-center justify-between gap-3 text-xs text-white/70">
          <span class="font-semibold">本帖媒体</span>
          <span>{{ attachmentIndex + 1 }} / {{ attachments.length }}</span>
        </div>
        <div
          v-if="hoverPreviewIndex >= 0 && attachments[hoverPreviewIndex] && (!isFullscreen || controlsVisible)"
          aria-hidden="true"
          class="pointer-events-none absolute bottom-[calc(100%+8px)] z-50 -translate-x-1/2 overflow-hidden rounded-xl border border-white/15 bg-black/95 p-1 shadow-2xl"
          :style="{ left: hoverPreviewX + 'px', width: hoverPreviewWidth + 'px', height: '268px' }"
        >
          <div class="relative h-full w-full overflow-hidden rounded-lg bg-white/5">
            <img
              v-if="attachments[hoverPreviewIndex].preview_ref && !failedPreviewKeys.has(attachments[hoverPreviewIndex].attachment_key)"
              :src="pawchiveMediaUrl(attachments[hoverPreviewIndex].preview_ref)"
              alt=""
              decoding="async"
              draggable="false"
              class="h-full w-full object-contain"
              @error="markPreviewFailed(attachments[hoverPreviewIndex].attachment_key)"
            />
            <span v-else class="flex h-full w-full items-center justify-center text-white/50"><ImageIcon :size="40" aria-hidden="true" /></span>
            <span v-if="attachments[hoverPreviewIndex].media_type === 'video'" class="absolute inset-0 flex items-center justify-center"><Play :size="38" fill="currentColor" aria-hidden="true" /></span>
            <span class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 to-transparent px-2 pb-2 pt-5 text-center text-xs font-semibold text-white">第 {{ hoverPreviewIndex + 1 }} / {{ attachments.length }} 项</span>
          </div>
        </div>
        <div ref="thumbnailStripRef" class="flex gap-2 overflow-x-auto pb-2 custom-scrollbar" @wheel.stop @scroll="updateHoverPreviewPosition">
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
            @mouseenter="showHoverPreview(index)"
            @mouseleave="hideHoverPreview(index)"
            @focus="showHoverPreview(index)"
            @blur="hideHoverPreview(index)"
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
      <p v-else-if="notice" role="status" class="text-xs text-white/60">{{ notice }}</p>
      <p v-if="downloadMessage" :role="downloadError ? 'alert' : 'status'" :class="downloadError ? 'text-red-300' : 'text-emerald-300'" class="text-sm">{{ downloadMessage }}</p>
      <div class="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between lg:gap-3">
        <p class="min-w-0 truncate text-xs text-white/65" :title="attachment.filename">本帖可播放附件 {{ attachmentIndex + 1 }} / {{ attachmentTotal }}<span class="ml-2">· {{ attachment.filename }}</span></p>
        <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
          <div class="flex flex-wrap items-center gap-2">
            <button v-if="attachment.media_type !== 'image'" type="button" :disabled="downloadBusy || busy" class="min-h-11 px-3 rounded-xl border border-white/15 flex items-center gap-1 text-sm disabled:opacity-50 cursor-pointer hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent" @click="emit('downloadCurrent')"><Download :size="15" />当前附件</button>
            <button type="button" :disabled="downloadBusy" class="min-h-11 px-3 rounded-xl border border-white/15 flex items-center gap-1 text-sm disabled:opacity-50 cursor-pointer hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent" @click="emit('downloadPost')">下载本帖</button>
            <label class="text-xs text-white/70 flex items-center gap-2">图片间隔
              <input type="number" min="1" max="300" :value="interval" class="w-16 min-h-11 rounded-lg bg-white/10 border border-white/15 px-2 text-white" @change="emit('update:interval', Math.min(300, Math.max(1, Number(($event.target as HTMLInputElement).value) || 5)))" />秒
            </label>
          </div>
          <div class="grid grid-cols-3 gap-2 sm:flex sm:items-center">
            <button type="button" :disabled="!hasPrevious || busy" class="min-h-11 px-3 rounded-xl border border-white/15 flex items-center justify-center gap-1 text-sm disabled:opacity-40 cursor-pointer hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent" @click="emit('previous')"><ArrowLeft :size="16" />上一项</button>
            <button type="button" class="min-h-11 px-3 rounded-xl border border-white/15 flex items-center justify-center gap-2 text-sm cursor-pointer hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent" :class="autoplay ? 'border-accent/60 bg-accent/15' : ''" :aria-pressed="autoplay" @click="emit('update:autoplay', !autoplay)"><Pause v-if="autoplay" :size="16" /><Play v-else :size="16" />{{ autoplay ? '暂停连播' : '自动连播' }}</button>
            <button type="button" :disabled="ended || busy" class="min-h-11 px-3 rounded-xl bg-accent flex items-center justify-center gap-1 text-sm font-bold disabled:opacity-40 cursor-pointer focus-visible:ring-2 focus-visible:ring-white" @click="emit('next')">{{ ended ? '范围末尾' : '下一项' }}<ArrowRight :size="16" /></button>
          </div>
        </div>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.pawchive-countdown {
  width: 100%;
  transform-origin: left;
  animation-name: pawchive-countdown;
  animation-timing-function: linear;
  animation-fill-mode: forwards;
}

@keyframes pawchive-countdown {
  from { transform: scaleX(0); }
  to { transform: scaleX(1); }
}
</style>

<style scoped>
.he-pawchive-viewer { height: var(--he-app-height, 100dvh); }
.he-pawchive-viewer > header { padding-top: calc(12px + env(safe-area-inset-top)); }
.he-pawchive-viewer > footer { padding-bottom: calc(12px + env(safe-area-inset-bottom)); }
@media (max-width: 599px) { .he-pawchive-viewer > header { gap: 4px; } }
</style>
