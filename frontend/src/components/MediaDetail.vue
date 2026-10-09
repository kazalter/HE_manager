<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { Maximize, Minimize, Trash2, X, FileQuestion, RefreshCw, PanelRightClose, PanelRightOpen, Pause, Play, Loader2 } from 'lucide-vue-next'
import { API_BASE_URL, STREAM_URL, authUrl, thumbnailUrl } from '../config'
import type { Media } from '../types'
import { audioPlaybackStore } from '../stores/audioPlaybackStore'
import { useCompactViewport } from '../composables/useCompactViewport'
const compact = useCompactViewport()
import MangaReader from './media-detail/MangaReader.vue'
import MetadataPanel from './media-detail/MetadataPanel.vue'
import VideoPlayer from './media-detail/VideoPlayer.vue'
import { UiButton } from './ui'
import { useMediaOverlayControls } from '../composables/useMediaOverlayControls'
import { useMediaProgress } from '../composables/useMediaProgress'
import { useVideoPlayback } from '../composables/useVideoPlayback'
import { useMediaKeyboard } from '../composables/useMediaKeyboard'
import { nextVideo } from '../utils/videoSequence'

const props = defineProps<{
  initialMedia: Media
  allMedia: Media[]
  hasAdjacentMediaPage?: (direction: -1 | 1) => boolean
  loadAdjacentMediaPage?: (direction: -1 | 1) => Promise<boolean>
}>()

const emit = defineEmits<{
  close: []
  updated: [media: Media]
  navigate: [media: Media]
}>()

const currentMedia = ref<Media>(props.initialMedia)
const currentPage = ref(0)
const totalMangaPages = ref<number | null>(null)
const mangaPageDimensions = ref<Array<[number, number] | null>>([])
const showMetadataPanel = ref(!compact.value && localStorage.getItem('he_detail_meta_panel') !== 'false')
const toggleMetadataPanel = () => {
  showMetadataPanel.value = !showMetadataPanel.value
  localStorage.setItem('he_detail_meta_panel', String(showMetadataPanel.value))
  nextTick(resizeVideoPlayer)
}

const isRechecking = ref(false)
const toastMessage = ref('')
const showToast = (msg: string) => {
  toastMessage.value = msg
  setTimeout(() => { toastMessage.value = '' }, 3000)
}

const videoUrl = computed(() => authUrl(`${STREAM_URL}/${currentMedia.value.id}`))
const coverUrl = computed(() => thumbnailUrl(currentMedia.value.cover_path))
const isImage = computed(() => currentMedia.value.media_type === 'image')
const isManga = computed(() => currentMedia.value.media_type === 'manga')
const isVideo = computed(() => currentMedia.value.media_type === 'video')
const isAudio = computed(() => currentMedia.value.media_type === 'audio')
watch(() => currentMedia.value, media => {
  if (media.media_type !== 'audio' || media.is_missing) return
  audioPlaybackStore.open(media)
  void nextTick(() => emit('close'))
}, { immediate: true })
const {
  isFullscreen,
  showControls,
  clickOnlyControls: clickOnlyViewerControls,
  setControlsHover,
  handleViewerClick,
  handleViewerDoubleClick,
  toggleFullscreen,
} = useMediaOverlayControls(isManga, isImage)

const overlayHeader = ref<HTMLElement | null>(null)
const isHeaderPointerOver = ref(false)
const isHeaderFocusWithin = ref(false)
const syncHeaderInteraction = () => setControlsHover(isHeaderPointerOver.value || isHeaderFocusWithin.value)
const setHeaderPointerOver = (over: boolean) => {
  isHeaderPointerOver.value = over
  syncHeaderInteraction()
}
const onHeaderFocusIn = () => {
  isHeaderFocusWithin.value = true
  syncHeaderInteraction()
}
const onHeaderFocusOut = (event: FocusEvent) => {
  if (overlayHeader.value?.contains(event.relatedTarget as Node | null)) return
  isHeaderFocusWithin.value = false
  syncHeaderInteraction()
}

watch(showControls, (visible) => {
  if (visible || !clickOnlyViewerControls.value) return
  const focused = document.activeElement
  if (focused instanceof HTMLElement && overlayHeader.value?.contains(focused)) focused.blur()
})

const currentIndex = computed(() => props.allMedia.findIndex(m => m.id === currentMedia.value.id))
const videoProgressPercent = computed(() => {
  if (!isVideo.value || !currentMedia.value.duration || currentMedia.value.progress <= 0) return 0
  return Math.min(100, Math.max(0, Math.round((currentMedia.value.progress / currentMedia.value.duration) * 100)))
})
const mangaPageTotal = computed(() => totalMangaPages.value || currentMedia.value.page_count || 0)
const mangaCurrentPageNumber = computed(() => {
  const current = currentPage.value + 1
  return mangaPageTotal.value ? Math.min(mangaPageTotal.value, Math.max(1, current)) : Math.max(1, current)
})
const mangaProgressPercent = computed(() => {
  if (!isManga.value || !mangaPageTotal.value) return 0
  return Math.min(100, Math.max(0, Math.round((mangaCurrentPageNumber.value / mangaPageTotal.value) * 100)))
})
const mangaProgressText = computed(() => {
  return mangaPageTotal.value ? `${mangaCurrentPageNumber.value} / ${mangaPageTotal.value}` : `${mangaCurrentPageNumber.value}`
})

const formatSize = (bytes: number) => {
  if (bytes === 0) return '本地目录'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

const formatDuration = (seconds: number | null) => {
  if (!seconds) return '未知'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return h > 0 ? `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}` : `${m}:${s.toString().padStart(2, '0')}`
}

const mediaTypeLabel = computed(() => {
  if (currentMedia.value.media_type === 'video') return '视频'
  if (currentMedia.value.media_type === 'manga') return '漫画'
  if (currentMedia.value.media_type === 'audio') return '音频'
  if (currentMedia.value.media_type === 'image') return '杂图'
  return '图片'
})

const progressText = computed(() => {
  if (isManga.value) return mangaProgressText.value
  if (!isVideo.value) return '-'
  return `${formatDuration(currentMedia.value.progress || 0)} / ${formatDuration(currentMedia.value.duration)}`
})

const applyMediaPatch = (media: Media) => {
  Object.assign(currentMedia.value, media)
  emit('updated', { ...currentMedia.value })
}

const updateMedia = async (
  payload: Partial<Pick<Media, 'duration' | 'favorite' | 'rating' | 'view_status' | 'progress' | 'title' | 'source_url' | 'source_site'>>,
  mediaId = currentMedia.value.id,
) => {
  const res = await axios.patch(`${API_BASE_URL}/media/${mediaId}`, payload)
  if (currentMedia.value.id === mediaId) {
    if (payload.progress !== undefined) {
      // A newer local position may already be queued while this PATCH was in flight.
      applyMediaPatch({ ...res.data, progress: currentMedia.value.progress,
        duration: currentMedia.value.duration, view_status: currentMedia.value.view_status })
    } else {
      applyMediaPatch(res.data)
    }
  } else {
    // A progress request may finish after playback already moved to another item.
    // Keep the parent list fresh without replacing the newly selected media.
    emit('updated', { ...res.data })
  }
}

const setRating = async (score: number) => {
  const previousMedia = { ...currentMedia.value, tags: [...currentMedia.value.tags] }
  const nextRating = currentMedia.value.rating === score ? 0 : score
  const optimisticMedia = { ...currentMedia.value, rating: nextRating }
  Object.assign(currentMedia.value, optimisticMedia)
  emit('updated', optimisticMedia)

  try {
    await updateMedia({ rating: nextRating })
  } catch (err) {
    Object.assign(currentMedia.value, previousMedia)
    emit('updated', previousMedia)
    console.error('Failed to update rating:', err)
    alert('评分保存失败。后端当前没有响应新版更新接口，请重新运行 he.ps1。')
  }
}

const addTag = async (name: string) => {
  if (!name.trim()) return
  const res = await axios.post(`${API_BASE_URL}/media/${currentMedia.value.id}/tags`, { name: name.trim() })
  applyMediaPatch(res.data)
}

const removeTag = async (tagId: number) => {
  const res = await axios.delete(`${API_BASE_URL}/media/${currentMedia.value.id}/tags/${tagId}`)
  applyMediaPatch(res.data)
}

const isNavigatingMedia = ref(false)
const navigateMedia = async (direction: -1 | 1) => {
  if (isNavigatingMedia.value) return

  let targetIndex = currentIndex.value + direction
  if (targetIndex < 0 || targetIndex >= props.allMedia.length) {
    if (!props.hasAdjacentMediaPage?.(direction) || !props.loadAdjacentMediaPage) return
    isNavigatingMedia.value = true
    try {
      if (!await props.loadAdjacentMediaPage(direction)) {
        if (props.hasAdjacentMediaPage(direction)) showToast('相邻页面加载失败，请重试')
        return
      }
      targetIndex = currentIndex.value + direction
    } finally {
      isNavigatingMedia.value = false
    }
  }

  const target = props.allMedia[targetIndex]
  if (!target) return
  if (isVideo.value) void saveVideoProgress(true)
  currentMedia.value = target
  currentPage.value = 0
  emit('navigate', target)
}

const nextMedia = () => { void navigateMedia(1) }
const prevMedia = () => { void navigateMedia(-1) }

const recheckMedia = async () => {
  if (isRechecking.value) return
  isRechecking.value = true
  try {
    const res = await axios.post(`${API_BASE_URL}/media/${currentMedia.value.id}/recheck`)
    applyMediaPatch(res.data)
    showToast('文件已恢复')
  } catch (err: any) {
    if (err.response?.status === 404) {
      showToast('文件仍不存在')
    } else {
      showToast('检查失败: ' + err.message)
    }
  } finally {
    isRechecking.value = false
  }
}

const removeMissingMedia = async () => {
  if (!confirm('确定要从媒体库中移除该记录吗？此操作不可逆。')) return
  try {
    await axios.delete(`${API_BASE_URL}/media/${currentMedia.value.id}`)
    emit('close')
    window.location.reload()
  } catch (err: any) {
    alert('移除失败: ' + err.message)
  }
}

const handleVideoSequenceEnded = () => {
  if (playMode.value === 'order' || playMode.value === 'shuffle') {
    const next = nextVideo(props.allMedia, currentMedia.value.id, playMode.value)
    if (!next) return
    currentMedia.value = next
    currentPage.value = 0
    emit('navigate', next)
  }
}

const {
  videoElement: progressVideoElement,
  bindVideo: bindVideoProgressEvents,
  unbindVideo: unbindVideoProgressEvents,
  saveVideoProgress,
} = useMediaProgress({
  media: currentMedia,
  currentPage,
  totalMangaPages,
  isVideo,
  isManga,
  updateMedia,
  emitUpdated: media => emit('updated', media),
  onVideoEnded: handleVideoSequenceEnded,
})


const reader = ref<InstanceType<typeof MangaReader> | null>(null)
const imagePages = computed(() => {
  const images = props.allMedia.filter(item => item.media_type === 'image' && !item.is_missing)
  return images.some(item => item.id === currentMedia.value.id) ? images : [currentMedia.value, ...images]
})
const imagePage = computed(() => Math.max(0, imagePages.value.findIndex(item => item.id === currentMedia.value.id)))
const imageDimensions = computed(() => imagePages.value.map(item => item.width && item.height ? [item.width, item.height] as [number, number] : null))
const selectImagePage = (page: number) => {
  const target = imagePages.value[page]
  if (!target || target.id === currentMedia.value.id) return
  currentMedia.value = target
  emit('navigate', target)
}
const setReaderPage = (page: number) => {
  if (isImage.value) selectImagePage(page)
  else currentPage.value = page
}
let imageBatchPromise: Promise<void> | null = null
let imageBatchDirection: -1 | 1 = 1
let viewerDisposed = false
onUnmounted(() => { viewerDisposed = true })
const loadImageBatch = async (direction: -1 | 1, navigate = false) => {
  if (!props.loadAdjacentMediaPage || viewerDisposed) return
  const originalId = currentMedia.value.id
  const originalLength = imagePages.value.length
  if (imageBatchPromise && imageBatchDirection !== direction) {
    const previous = imageBatchPromise
    await previous
    if (viewerDisposed || currentMedia.value.id !== originalId) return
    if (imageBatchPromise === previous) imageBatchPromise = null
    return loadImageBatch(direction, navigate)
  }
  const step = direction > 0
    ? Math.min(reader.value?.stepSize ?? 1, originalLength - imagePage.value)
    : reader.value?.stepSize ?? 1
  if (!imageBatchPromise) {
    imageBatchDirection = direction
    imageBatchPromise = (async () => {
      // Bound speculative list requests when a mixed list contains few images.
      for (let attempt = 0; attempt < 3 && !viewerDisposed && props.hasAdjacentMediaPage?.(direction); attempt++) {
        if (!await props.loadAdjacentMediaPage!(direction)) {
          if (!viewerDisposed && props.hasAdjacentMediaPage?.(direction)) showToast('图片列表加载失败，请重试')
          break
        }
        if (imagePages.value.length > originalLength) break
      }
    })()
  }
  const pending = imageBatchPromise
  try {
    await pending
    if (!viewerDisposed && navigate && currentMedia.value.id === originalId) selectImagePage(imagePage.value + direction * step)
  } finally { if (imageBatchPromise === pending) imageBatchPromise = null }
}
watch(() => [isImage.value, imagePage.value], () => {
  if (isImage.value && imagePages.value.length - imagePage.value <= 4 && props.hasAdjacentMediaPage?.(1)) {
    void loadImageBatch(1)
  }
}, { immediate: true })

watch(
  () => [currentMedia.value.id, currentMedia.value.media_type] as const,
  async () => {
    const media = currentMedia.value
    currentPage.value = media.media_type === 'manga' ? Math.max(0, media.progress || 0) : 0
    if (media.media_type !== 'manga') return
    totalMangaPages.value = null
    mangaPageDimensions.value = []
    if (media.is_missing) return
    try {
      const res = await axios.get(`${API_BASE_URL}/manga/${media.id}/pages`, { params: { include_dimensions: true } })
      if (currentMedia.value.id !== media.id) return
      mangaPageDimensions.value = res.data.page_dimensions || []
      totalMangaPages.value = res.data.total_pages
      void axios.post(`${API_BASE_URL}/manga/${media.id}/thumbnails/generate`).catch(() => {})
    } catch {
      if (currentMedia.value.id === media.id) totalMangaPages.value = null
    }
  },
  { immediate: true },
)

const {
  playMode,
  setArtContainer,
  beginVideoLongPress,
  finishVideoLongPress,
  seekVideo,
  isArtFullscreen,
  exitArtFullscreen,
  resizeVideoPlayer,
} = useVideoPlayback({
  media: currentMedia,
  isVideo,
  videoUrl,
  videoElement: progressVideoElement,
  bindVideo: bindVideoProgressEvents,
  unbindVideo: unbindVideoProgressEvents,
  saveProgress: saveVideoProgress,
  onError: showToast,
})

const nextPage = () => {
  const step = localStorage.getItem(compact.value ? 'he_manga_read_mode_mobile' : 'he_manga_read_mode') === 'double' ? 2 : 1
  if (totalMangaPages.value === null || currentPage.value < totalMangaPages.value - 1) {
    const max = totalMangaPages.value === null ? Number.MAX_SAFE_INTEGER : totalMangaPages.value - 1
    currentPage.value = Math.min(max, currentPage.value + step)
  }
}

const AUTO_ADVANCE_SECONDS_KEY = 'he_auto_advance_seconds'
const savedAutoAdvanceSeconds = Number(localStorage.getItem(AUTO_ADVANCE_SECONDS_KEY))
const autoAdvanceSeconds = ref(
  Number.isFinite(savedAutoAdvanceSeconds) && savedAutoAdvanceSeconds >= 1
    ? Math.min(300, Math.round(savedAutoAdvanceSeconds))
    : 5,
)
const autoAdvanceSecondsInput = ref(String(autoAdvanceSeconds.value))
const isAutoAdvancing = ref(false)
const toggleAutoAdvance = (event: MouseEvent) => {
  isAutoAdvancing.value = !isAutoAdvancing.value
  if (event.detail > 0) (event.currentTarget as HTMLElement).blur()
}
const isEditingAutoAdvanceSeconds = ref(false)
const isDocumentVisible = ref(!document.hidden)
let autoAdvanceTimer: number | undefined

const nextImageIndex = computed(() => currentIndex.value === -1 ? -1 : props.allMedia.findIndex(
  (item, index) => index > currentIndex.value && item.media_type === 'image' && !item.is_missing,
))
const canAutoAdvance = computed(() => {
  if (currentMedia.value.is_missing) return false
  if (isImage.value) return nextImageIndex.value !== -1 || !!props.hasAdjacentMediaPage?.(1)
  if (isManga.value) return mangaPageTotal.value > 0 && currentPage.value < mangaPageTotal.value - 1
  return false
})

const clearAutoAdvanceTimer = () => {
  if (autoAdvanceTimer !== undefined) {
    window.clearTimeout(autoAdvanceTimer)
    autoAdvanceTimer = undefined
  }
}

const commitAutoAdvanceSeconds = () => {
  const seconds = Number(autoAdvanceSecondsInput.value)
  if (!Number.isFinite(seconds) || seconds < 1) {
    autoAdvanceSecondsInput.value = String(autoAdvanceSeconds.value)
    return
  }
  autoAdvanceSeconds.value = Math.min(300, Math.max(1, Math.round(seconds)))
  autoAdvanceSecondsInput.value = String(autoAdvanceSeconds.value)
  localStorage.setItem(AUTO_ADVANCE_SECONDS_KEY, String(autoAdvanceSeconds.value))
}

const finishEditingAutoAdvanceSeconds = () => {
  commitAutoAdvanceSeconds()
  isEditingAutoAdvanceSeconds.value = false
}

const advanceAutomatically = async () => {
  autoAdvanceTimer = undefined
  if (!isAutoAdvancing.value || !isDocumentVisible.value || !canAutoAdvance.value) return
  if (isImage.value) {
    if (isNavigatingMedia.value) return
    isNavigatingMedia.value = true
    try {
      const step = reader.value?.stepSize ?? 1
      let nextIndex = nextImageIndex.value
      const nextSpread = imagePages.value[imagePage.value + step]
      if (nextSpread) nextIndex = props.allMedia.findIndex(item => item.id === nextSpread.id)
      while (nextIndex === -1 && props.hasAdjacentMediaPage?.(1) && props.loadAdjacentMediaPage) {
        const previousLength = props.allMedia.length
        await loadImageBatch(1)
        if (viewerDisposed) return
        if (props.allMedia.length === previousLength) {
          if (props.hasAdjacentMediaPage(1)) showToast('后续图片加载失败，自动播放已暂停')
          break
        }
        nextIndex = nextImageIndex.value
      }
      const next = props.allMedia[nextIndex]
      if (next) {
        currentMedia.value = next
        currentPage.value = 0
        emit('navigate', next)
      } else {
        isAutoAdvancing.value = false
      }
    } finally {
      isNavigatingMedia.value = false
    }
  } else if (isManga.value) {
    nextPage()
  }
}

watch(
  [isAutoAdvancing, autoAdvanceSeconds, isEditingAutoAdvanceSeconds, isDocumentVisible, canAutoAdvance,
    () => currentMedia.value.id, currentPage, mangaPageTotal],
  () => {
    clearAutoAdvanceTimer()
    if (!canAutoAdvance.value) {
      isAutoAdvancing.value = false
      return
    }
    if (isAutoAdvancing.value && isDocumentVisible.value && !isEditingAutoAdvanceSeconds.value) {
      autoAdvanceTimer = window.setTimeout(advanceAutomatically, autoAdvanceSeconds.value * 1000)
    }
  },
)

const onVisibilityChange = () => {
  isDocumentVisible.value = !document.hidden
}

onMounted(() => document.addEventListener('visibilitychange', onVisibilityChange))
onUnmounted(() => {
  clearAutoAdvanceTimer()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})

const handleKeydown = (e: KeyboardEvent) => {
  const target = e.target as HTMLElement | null
  if (
    target &&
    (target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.isContentEditable)
  ) {
    return
  }

  if (e.key === 'Escape') {
    if (document.fullscreenElement || (isVideo.value && isArtFullscreen())) {
      if (isVideo.value) exitArtFullscreen()
      else void document.exitFullscreen()
      e.preventDefault()
      e.stopImmediatePropagation()
      return
    }
    emit('close')
    e.preventDefault()
    e.stopImmediatePropagation()
  }

  if (e.key === 'ArrowRight') {
    if (isManga.value) {
      reader.value?.nextPage()
      e.preventDefault()
      e.stopImmediatePropagation()
    } else if (isVideo.value && progressVideoElement.value) {
      e.preventDefault()
      e.stopImmediatePropagation()
      if (!e.repeat) beginVideoLongPress('forward')
    } else {
      if (isImage.value) reader.value?.nextPage()
      else nextMedia()
      e.preventDefault()
      e.stopImmediatePropagation()
    }
  }

  if (e.key === 'ArrowLeft') {
    if (isManga.value) {
      reader.value?.previousPage()
      e.preventDefault()
      e.stopImmediatePropagation()
    } else if (isVideo.value && progressVideoElement.value) {
      e.preventDefault()
      e.stopImmediatePropagation()
      if (!e.repeat) beginVideoLongPress('rewind')
    } else {
      if (isImage.value) reader.value?.previousPage()
      else prevMedia()
      e.preventDefault()
      e.stopImmediatePropagation()
    }
  }
}

const handleKeyup = (e: KeyboardEvent) => {
  const target = e.target as HTMLElement | null
  if (
    target &&
    (target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.isContentEditable)
  ) {
    return
  }

  if (e.key === 'ArrowRight') {
    if (isVideo.value && progressVideoElement.value) {
      e.preventDefault()
      e.stopImmediatePropagation()
      seekVideo('forward')
    }
  }

  if (e.key === 'ArrowLeft') {
    if (isVideo.value && progressVideoElement.value) {
      e.preventDefault()
      e.stopImmediatePropagation()
      seekVideo('rewind')
    }
  }
}

const handleWindowBlur = () => {
  finishVideoLongPress(false)
}

useMediaKeyboard(handleKeydown, handleKeyup, handleWindowBlur)

</script>

<template>
  <Teleport to="body">
    <div v-if="!isAudio || currentMedia.is_missing" role="dialog" aria-modal="true" :aria-label="currentMedia.title" class="he-media-overlay fixed inset-0 z-[200] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/80" @click="emit('close')"></div>

      <div class="he-media-layout relative flex h-full w-full overflow-hidden bg-black" :class="{ 'is-video': isVideo, 'show-mobile-metadata': compact && showMetadataPanel }">
        <section class="relative flex min-w-0 flex-1 flex-col bg-black">
          <header
            ref="overlayHeader"
            @mouseenter="setHeaderPointerOver(true)"
            @mouseleave="setHeaderPointerOver(false)"
            @focusin="onHeaderFocusIn"
            @focusout="onHeaderFocusOut"
            :class="isAudio
              ? 'relative shrink-0 border-b border-white/10 bg-black opacity-100 translate-y-0'
              : [
                  'absolute inset-x-0 top-0 bg-gradient-to-b from-black/75 via-black/35 to-transparent',
                  showControls || (isAutoAdvancing && !clickOnlyViewerControls)
                    ? 'opacity-100 translate-y-0'
                    : clickOnlyViewerControls
                      ? 'opacity-0 -translate-y-3 pointer-events-none'
                      : 'opacity-0 -translate-y-3 hover:opacity-100 hover:translate-y-0',
                ]"
            class="he-viewer-header z-50 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 pb-6 pt-3 transition-[opacity,transform] duration-200 ease-out focus-within:pointer-events-auto focus-within:translate-y-0 focus-within:opacity-100 sm:flex-nowrap sm:px-6 sm:pt-4"
          >
            <h2 class="min-w-0 flex-1 select-none truncate text-body font-medium text-white sm:text-heading sm:font-semibold">{{ currentMedia.title }}</h2>
            <div class="he-viewer-actions flex shrink-0 items-center gap-1 rounded-2xl bg-black/70 p-1 text-white">
              <div
                v-if="(isImage || isManga) && !currentMedia.is_missing"
                role="group"
                aria-label="自动播放设置"
                class="flex items-center gap-1"
                @click.stop
              >
                <button
                  type="button"
                  class="he-chrome-btn gap-1.5 px-2.5 text-meta font-medium disabled:cursor-not-allowed disabled:opacity-40"
                  :class="isAutoAdvancing ? 'bg-accent text-on-accent hover:bg-accent/90' : 'text-white/85 hover:bg-white/10 hover:text-white'"
                  :disabled="!isAutoAdvancing && !canAutoAdvance"
                  :aria-label="isAutoAdvancing ? '暂停自动播放' : '开始自动播放'"
                  :aria-pressed="isAutoAdvancing"
                  :title="isAutoAdvancing ? '暂停自动播放' : canAutoAdvance ? '开始自动播放' : isManga ? '已到最后一页' : '没有下一张图片'"
                  @click="toggleAutoAdvance"
                >
                  <Pause v-if="isAutoAdvancing" :size="16" aria-hidden="true" />
                  <Play v-else :size="16" aria-hidden="true" />
                  <span class="hidden min-[420px]:inline">{{ isAutoAdvancing ? '暂停' : '自动播放' }}</span>
                </button>
                <label class="flex items-center gap-1.5 pr-1.5 text-meta text-white/70">
                  <span class="sr-only">自动播放间隔（秒）</span>
                  <input
                    v-model="autoAdvanceSecondsInput"
                    type="number"
                    min="1"
                    max="300"
                    step="1"
                    inputmode="numeric"
                    class="he-seconds-input h-9 w-11 rounded-lg border border-white/15 bg-white/10 text-center text-body tabular-nums text-white transition-colors hover:border-white/25 focus:border-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 pointer-coarse:h-11"
                    aria-label="自动播放间隔，秒"
                    title="自动播放间隔，1 至 300 秒"
                    @focus="isEditingAutoAdvanceSeconds = true"
                    @change="commitAutoAdvanceSeconds"
                    @blur="finishEditingAutoAdvanceSeconds"
                    @keydown.enter="finishEditingAutoAdvanceSeconds"
                  />
                  <span>秒</span>
                </label>
                <span class="mx-0.5 h-5 w-px bg-white/15" aria-hidden="true"></span>
              </div>
              <button
                v-if="!isFullscreen && !(compact && isVideo)"
                type="button"
                class="he-chrome-btn w-9 text-white/80 hover:bg-white/10 hover:text-white pointer-coarse:w-11"
                :class="showMetadataPanel ? 'bg-white/10 text-white' : ''"
                :aria-label="showMetadataPanel ? '收起媒体信息' : '显示媒体信息'" :aria-expanded="showMetadataPanel"
                :title="showMetadataPanel ? '收起信息侧栏' : '展开信息侧栏'"
                @click="toggleMetadataPanel"
              >
                <PanelRightClose v-if="showMetadataPanel" :size="18" aria-hidden="true" />
                <PanelRightOpen v-else :size="18" aria-hidden="true" />
              </button>
              <button v-if="!isVideo" type="button" class="he-chrome-btn w-9 text-white/80 hover:bg-white/10 hover:text-white pointer-coarse:w-11" :aria-label="isFullscreen ? '退出全屏' : '全屏'" :title="isFullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen">
                <Minimize v-if="isFullscreen" :size="18" aria-hidden="true" />
                <Maximize v-else :size="18" aria-hidden="true" />
              </button>
              <button type="button" class="he-chrome-btn w-9 text-white/80 hover:bg-white/10 hover:text-white pointer-coarse:w-11" aria-label="返回媒体列表" title="关闭" @click="emit('close')">
                <X :size="20" aria-hidden="true" />
              </button>
            </div>
          </header>

          <div
            v-if="isNavigatingMedia"
            role="status"
            aria-live="polite"
            class="absolute bottom-6 left-1/2 z-[120] flex -translate-x-1/2 items-center gap-2 rounded-full bg-black/80 px-4 py-2 text-meta text-white/90 ring-1 ring-inset ring-white/10"
          >
            <Loader2 :size="16" class="animate-spin" aria-hidden="true" />
            <span>正在加载媒体…</span>
          </div>

          <div v-if="toastMessage && !currentMedia.is_missing" role="status" class="absolute bottom-44 left-1/2 z-[120] max-w-[calc(100%-2rem)] -translate-x-1/2 rounded-2xl bg-black/85 px-4 py-2.5 text-body text-white ring-1 ring-inset ring-white/10">{{ toastMessage }}</div>

          <div v-if="currentMedia.is_missing" class="absolute inset-0 z-[100] flex flex-col items-center justify-center bg-black/85 p-6">
            <div class="w-full max-w-md rounded-3xl border border-line-strong bg-surface-3 p-6 text-center shadow-modal sm:p-8">
              <div class="mx-auto mb-4 grid size-12 place-items-center rounded-2xl border border-danger/25 bg-danger/10 text-danger" aria-hidden="true">
                <FileQuestion :size="22" />
              </div>
              <h3 class="text-heading font-semibold text-ink">文件丢失</h3>
              <p class="mx-auto mt-1.5 max-w-sm text-meta text-subtle">
                系统无法找到原文件。可能是文件已被删除、移动，或所在的外部存储设备未连接。
              </p>
              <div class="mt-6 flex flex-col justify-center gap-2 sm:flex-row">
                <UiButton variant="secondary" size="lg" :loading="isRechecking" @click="recheckMedia">
                  <template #icon><RefreshCw :size="16" /></template>
                  重新检查
                </UiButton>
                <UiButton variant="danger" size="lg" @click="removeMissingMedia">
                  <template #icon><Trash2 :size="16" /></template>
                  从媒体库移除
                </UiButton>
              </div>
            </div>
            <div v-if="toastMessage" role="status" class="absolute bottom-10 left-1/2 -translate-x-1/2 rounded-2xl border border-line-strong bg-surface-3 px-4 py-2.5 text-body text-ink shadow-pop">
              {{ toastMessage }}
            </div>
          </div>

          <VideoPlayer v-else-if="isVideo" :cover-url="coverUrl" @ready="setArtContainer" />

          <MangaReader
            v-else-if="isManga || isImage"
            ref="reader"
            :key="isImage ? 'images' : `manga-${currentMedia.id}`"
            :current-page="isImage ? imagePage : currentPage"
            :media="currentMedia"
            :image-pages="isImage ? imagePages : undefined"
            :has-next-batch="isImage && !!hasAdjacentMediaPage?.(1)"
            :has-previous-batch="isImage && !!hasAdjacentMediaPage?.(-1)"
            :total-pages="isImage ? imagePages.length : totalMangaPages"
            :page-dimensions="isImage ? imageDimensions : mangaPageDimensions"
            :show-controls="showControls"
            :click-only-controls="clickOnlyViewerControls"
            :progress-text="isImage ? `${imagePage + 1} / ${imagePages.length}` : mangaProgressText"
            :progress-percent="isImage ? Math.round((imagePage + 1) / imagePages.length * 100) : mangaProgressPercent"
            @update:current-page="setReaderPage"
            @boundary="loadImageBatch($event, true)"
            @load-more="loadImageBatch(1)"
            @viewer-click="handleViewerClick"
            @viewer-double-click="handleViewerDoubleClick"
            @controls-hover="setControlsHover"
          />

          <MetadataPanel
            v-if="isVideo && compact && !currentMedia.is_missing"
            inline
            :media="currentMedia"
            :cover-url="coverUrl"
            :media-type-label="mediaTypeLabel"
            :video-progress-percent="videoProgressPercent"
            :manga-progress-percent="mangaProgressPercent"
            :manga-progress-text="mangaProgressText"
            :manga-page-total="mangaPageTotal"
            @toggle-favorite="updateMedia({ favorite: !currentMedia.favorite })"
            @set-rating="setRating"
            @add-tag="addTag"
            @remove-tag="removeTag"
          />

          <div v-if="isVideo && !compact" class="video-summary min-[1100px]:hidden shrink-0 border-t border-line bg-background px-6 py-4">
            <h3 class="truncate text-heading font-semibold text-ink" :title="currentMedia.title">{{ currentMedia.title }}</h3>
            <p class="mt-1 flex flex-wrap items-center gap-x-2 text-meta text-subtle tabular-nums">
              <span>{{ mediaTypeLabel }}</span>
              <span class="text-faint" aria-hidden="true">·</span>
              <span>{{ progressText }}</span>
              <span class="text-faint" aria-hidden="true">·</span>
              <span>已看 {{ videoProgressPercent }}%</span>
              <span class="text-faint" aria-hidden="true">·</span>
              <span>{{ formatSize(currentMedia.file_size) }}</span>
            </p>
            <div class="mt-3 h-1 overflow-hidden rounded-sm bg-surface-3">
              <div class="h-full rounded-sm bg-accent" :style="{ width: `${videoProgressPercent}%` }"></div>
            </div>
          </div>
        </section>

        <button v-if="compact && showMetadataPanel && showControls" type="button" class="he-metadata-scrim" aria-label="关闭媒体信息背景" tabindex="-1" @click="toggleMetadataPanel"></button>
        <MetadataPanel
          v-if="!isFullscreen && showMetadataPanel && !(compact && isVideo) && (showControls || (!isManga && !isImage))"
          :media="currentMedia"
          :cover-url="coverUrl"
          :media-type-label="mediaTypeLabel"
          :video-progress-percent="videoProgressPercent"
          :manga-progress-percent="mangaProgressPercent"
          :manga-progress-text="mangaProgressText"
          :manga-page-total="mangaPageTotal"
          @close="toggleMetadataPanel"
          @toggle-favorite="updateMedia({ favorite: !currentMedia.favorite })"
          @set-rating="setRating"
          @add-tag="addTag"
          @remove-tag="removeTag"
        />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.he-media-overlay { height: var(--he-app-height, 100dvh); padding-left: env(safe-area-inset-left); padding-right: env(safe-area-inset-right); }
.he-viewer-header { padding-top: calc(12px + env(safe-area-inset-top)); }
.he-chrome-btn {
  display: inline-flex;
  height: 36px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  transition: background-color var(--duration-fast, 120ms) var(--ease-out, ease-out), color var(--duration-fast, 120ms) var(--ease-out, ease-out);
}
@media (pointer: coarse) {
  .he-chrome-btn { height: 44px; min-width: 44px; }
}
.he-seconds-input { -moz-appearance: textfield; }
.he-seconds-input::-webkit-outer-spin-button,
.he-seconds-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.he-metadata-scrim { position: absolute; inset: 0; z-index: 55; background: rgb(0 0 0 / 0.6); }
@media (max-width: 899px) {
  .he-viewer-header { padding-inline: 12px; padding-bottom: 16px; }
  .he-media-layout:not(.is-video) .he-viewer-header h2 { flex-basis: 100%; }
  .he-media-layout:not(.is-video) .he-viewer-header { justify-content: flex-end; }
  .he-viewer-header [aria-label="自动播放设置"] button span { display: none; }
  .he-media-layout.is-video > section { overflow-y: auto; overscroll-behavior: contain; }
  .he-media-layout.is-video .he-viewer-header { position: relative; flex-wrap: nowrap; opacity: 1; transform: none; pointer-events: auto; background: #000; padding-bottom: 8px; }
  .he-media-layout.is-video .he-viewer-actions { background: transparent; padding: 0; }
  .he-media-layout.is-video :deep(.he-video-stage) { flex: 0 0 auto; aspect-ratio: 16 / 9; width: 100%; }
}
@media (max-width: 899px) and (orientation: landscape) {
  .he-media-layout.is-video :deep(.he-video-stage) { flex: 1 1 0; aspect-ratio: auto; min-height: 0; }
  .he-media-layout.is-video :deep(.he-metadata-inline) { display: none; }
}
@media (max-height: 650px) {
  .video-summary { display: none; }
}
</style>
