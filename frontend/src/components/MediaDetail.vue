<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { Maximize, Minimize, Trash2, X, FileQuestion, RefreshCw, PanelRightClose, PanelRightOpen, Pause, Play, Loader2 } from 'lucide-vue-next'
import { API_BASE_URL, STREAM_URL, authUrl, thumbnailUrl } from '../config'
import type { Media } from '../types'
import { audioPlaybackStore } from '../stores/audioPlaybackStore'
import { useCompactViewport } from '../composables/useCompactViewport'
const compact = useCompactViewport()
import ImageViewer from './media-detail/ImageViewer.vue'
import MangaReader from './media-detail/MangaReader.vue'
import MetadataPanel from './media-detail/MetadataPanel.vue'
import VideoPlayer from './media-detail/VideoPlayer.vue'
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

const imageUrl = computed(() => authUrl(`${API_BASE_URL}/stream/${currentMedia.value.id}`))
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


const preloadedImageUrls = new Set<string>()

const preloadAdjacentImages = () => {
  if (!isImage.value || currentIndex.value === -1 || !props.allMedia.length) return

  const targets = [
    currentIndex.value + 1,
    currentIndex.value + 2,
    currentIndex.value - 1,
  ]

  for (const idx of targets) {
    if (idx >= 0 && idx < props.allMedia.length) {
      const item = props.allMedia[idx]
      if (item && item.media_type === 'image') {
        const streamUrl = authUrl(`${API_BASE_URL}/stream/${item.id}`)
        if (!preloadedImageUrls.has(streamUrl)) {
          preloadedImageUrls.add(streamUrl)
          if (typeof Image !== 'undefined') {
            const img = new Image()
            img.src = streamUrl
          }
        }
      }
    }
  }

  if (preloadedImageUrls.size > 50) {
    const list = Array.from(preloadedImageUrls)
    preloadedImageUrls.clear()
    for (const url of list.slice(-25)) {
      preloadedImageUrls.add(url)
    }
  }
}

watch(
  () => [currentMedia.value.id, currentMedia.value.media_type] as const,
  async () => {
    const media = currentMedia.value
    currentPage.value = media.media_type === 'manga' ? Math.max(0, media.progress || 0) : 0
    if (media.media_type === 'image') preloadAdjacentImages()
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

const prevPage = () => {
  const step = localStorage.getItem(compact.value ? 'he_manga_read_mode_mobile' : 'he_manga_read_mode') === 'double' ? 2 : 1
  if (currentPage.value > 0) currentPage.value = Math.max(0, currentPage.value - step)
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
      let nextIndex = nextImageIndex.value
      while (nextIndex === -1 && props.hasAdjacentMediaPage?.(1) && props.loadAdjacentMediaPage) {
        if (!await props.loadAdjacentMediaPage(1)) {
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
      nextPage()
      e.preventDefault()
      e.stopImmediatePropagation()
    } else if (isVideo.value && progressVideoElement.value) {
      e.preventDefault()
      e.stopImmediatePropagation()
      if (!e.repeat) beginVideoLongPress('forward')
    } else {
      nextMedia()
      e.preventDefault()
      e.stopImmediatePropagation()
    }
  }

  if (e.key === 'ArrowLeft') {
    if (isManga.value) {
      prevPage()
      e.preventDefault()
      e.stopImmediatePropagation()
    } else if (isVideo.value && progressVideoElement.value) {
      e.preventDefault()
      e.stopImmediatePropagation()
      if (!e.repeat) beginVideoLongPress('rewind')
    } else {
      prevMedia()
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
onUnmounted(() => preloadedImageUrls.clear())

</script>

<template>
  <Teleport to="body">
    <div v-if="!isAudio || currentMedia.is_missing" role="dialog" aria-modal="true" :aria-label="currentMedia.title" class="he-media-overlay fixed inset-0 z-[200] flex items-center justify-center">
      <div class="absolute inset-0 bg-background/85 backdrop-blur-2xl" @click="emit('close')"></div>

      <div class="he-media-layout relative w-full h-full bg-[#060606] shadow-2xl flex overflow-hidden" :class="{ 'is-video': isVideo, 'show-mobile-metadata': compact && showMetadataPanel }">
        <section class="relative flex-1 min-w-0 bg-black flex flex-col">
          <header
            ref="overlayHeader"
            @mouseenter="setHeaderPointerOver(true)"
            @mouseleave="setHeaderPointerOver(false)"
            @focusin="onHeaderFocusIn"
            @focusout="onHeaderFocusOut"
            :class="isAudio
              ? 'relative shrink-0 border-b border-white/10 bg-black/80 opacity-100 translate-y-0'
              : [
                  'absolute top-0 left-0 right-0 bg-gradient-to-b from-black/80 to-transparent',
                  showControls || (isAutoAdvancing && !clickOnlyViewerControls)
                    ? 'opacity-100 translate-y-0'
                    : clickOnlyViewerControls
                      ? 'opacity-0 -translate-y-3 pointer-events-none'
                      : 'opacity-0 -translate-y-3 hover:opacity-100 hover:translate-y-0',
                ]"
            class="he-viewer-header flex flex-wrap sm:flex-nowrap items-center justify-between gap-2 px-4 sm:px-6 py-3 sm:py-5 z-50 transition-all duration-300 focus-within:opacity-100 focus-within:translate-y-0 focus-within:pointer-events-auto"
          >
            <h2 class="w-full sm:w-auto sm:grow min-w-0 text-lg font-bold truncate sm:pr-4 text-white/95 drop-shadow-xl select-none">{{ currentMedia.title }}</h2>
            <div class="flex w-full sm:w-auto items-center justify-end gap-2">
              <div
                v-if="(isImage || isManga) && !currentMedia.is_missing"
                role="group"
                aria-label="自动播放设置"
                class="flex items-center gap-2 rounded-xl border border-white/20 bg-black/70 p-1 text-white backdrop-blur-md"
                @click.stop
              >
                <button
                  type="button"
                  class="inline-flex h-11 min-w-11 items-center justify-center gap-2 rounded-lg px-2.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-black disabled:cursor-not-allowed disabled:opacity-40"
                  :class="isAutoAdvancing ? 'bg-accent/25 text-accent hover:bg-accent/35' : 'bg-white/10 text-white hover:bg-white/20'"
                  :disabled="!isAutoAdvancing && !canAutoAdvance"
                  :aria-label="isAutoAdvancing ? '暂停自动播放' : '开始自动播放'"
                  :aria-pressed="isAutoAdvancing"
                  :title="isAutoAdvancing ? '暂停自动播放' : canAutoAdvance ? '开始自动播放' : isManga ? '已到最后一页' : '没有下一张图片'"
                  @click="toggleAutoAdvance"
                >
                  <Pause v-if="isAutoAdvancing" :size="18" />
                  <Play v-else :size="18" />
                  <span class="hidden min-[420px]:inline">{{ isAutoAdvancing ? '暂停' : '自动播放' }}</span>
                </button>
                <label class="flex items-center gap-1.5 pr-1.5 text-sm font-medium text-white/80">
                  <span class="sr-only">自动播放间隔（秒）</span>
                  <input
                    v-model="autoAdvanceSecondsInput"
                    type="number"
                    min="1"
                    max="300"
                    step="1"
                    inputmode="numeric"
                    class="h-11 w-12 rounded-lg border border-white/25 bg-white/10 text-center font-mono text-base text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-black"
                    aria-label="自动播放间隔，秒"
                    title="自动播放间隔，1 至 300 秒"
                    @focus="isEditingAutoAdvanceSeconds = true"
                    @change="commitAutoAdvanceSeconds"
                    @blur="finishEditingAutoAdvanceSeconds"
                    @keydown.enter="finishEditingAutoAdvanceSeconds"
                  />
                  <span>秒</span>
                </label>
              </div>
              <button
                v-if="!isFullscreen"
                @click="toggleMetadataPanel"
                class="w-11 h-11 rounded-xl bg-black/35 backdrop-blur-md hover:bg-black/55 text-white/65 hover:text-white transition-all"
                :aria-label="showMetadataPanel ? '收起媒体信息' : '显示媒体信息'" :aria-expanded="showMetadataPanel"
                :title="showMetadataPanel ? '收起信息侧栏' : '展开信息侧栏'"
              >
                <PanelRightClose v-if="showMetadataPanel" :size="19" class="mx-auto" />
                <PanelRightOpen v-else :size="19" class="mx-auto" />
              </button>
              <button v-if="!isVideo" @click="toggleFullscreen" class="w-11 h-11 rounded-xl bg-black/35 backdrop-blur-md hover:bg-black/55 text-white/65 hover:text-white transition-all" :title="isFullscreen ? '退出全屏' : '全屏'">
                <Minimize v-if="isFullscreen" :size="19" class="mx-auto" />
                <Maximize v-else :size="19" class="mx-auto" />
              </button>
              <button @click="emit('close')" class="w-11 h-11 rounded-xl bg-red-500/20 backdrop-blur-md hover:bg-red-500/40 text-red-100 hover:text-white transition-all" aria-label="返回媒体列表" title="关闭">
                <X :size="20" class="mx-auto" />
              </button>
            </div>
          </header>

          <div
            v-if="isNavigatingMedia"
            role="status"
            aria-live="polite"
            class="absolute bottom-6 left-1/2 z-[120] flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/15 bg-black/80 px-4 py-2 text-sm text-white/85 shadow-xl backdrop-blur-md"
          >
            <Loader2 :size="16" class="animate-spin text-accent" />
            <span>正在加载媒体…</span>
          </div>

          <div v-if="currentMedia.is_missing" class="absolute inset-0 z-[100] bg-black/85 flex flex-col items-center justify-center p-8 backdrop-blur-md">
            <div class="bg-red-500/10 border border-red-500/20 rounded-3xl p-8 max-w-md w-full text-center shadow-2xl">
              <div class="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-5 shadow-inner shadow-red-500/20">
                <FileQuestion :size="32" class="text-red-400" />
              </div>
              <h3 class="text-2xl font-black text-red-400 mb-3 tracking-tight">文件丢失</h3>
              <p class="text-[15px] text-white/60 leading-relaxed mb-8">
                系统无法找到原文件。<br>可能是文件已被删除、移动，或所在的外部存储设备未连接。
              </p>
              <div class="flex flex-col sm:flex-row gap-3 justify-center">
                <button @click="recheckMedia" class="px-6 py-3 rounded-xl bg-white/10 hover:bg-white/20 text-white font-bold transition-all flex items-center justify-center gap-2 flex-1 shadow-lg shadow-black/50">
                  <RefreshCw :size="18" :class="{ 'animate-spin': isRechecking }" />
                  重新检查
                </button>
                <button @click="removeMissingMedia" class="px-6 py-3 rounded-xl bg-red-500 hover:bg-red-600 text-white font-bold transition-all flex items-center justify-center gap-2 flex-1 shadow-lg shadow-red-500/20">
                  <Trash2 :size="18" />
                  从媒体库移除
                </button>
              </div>
            </div>
            <div v-if="toastMessage" class="absolute bottom-10 left-1/2 -translate-x-1/2 bg-black/90 border border-white/10 text-white px-6 py-3 rounded-xl font-bold shadow-2xl transition-all">
              {{ toastMessage }}
            </div>
          </div>

          <VideoPlayer v-else-if="isVideo" :cover-url="coverUrl" @ready="setArtContainer" />

          <MangaReader
            v-else-if="isManga"
            v-model:current-page="currentPage"
            :media="currentMedia"
            :total-pages="totalMangaPages"
            :page-dimensions="mangaPageDimensions"
            :show-controls="showControls"
            :click-only-controls="clickOnlyViewerControls"
            :progress-text="mangaProgressText"
            :progress-percent="mangaProgressPercent"
            @viewer-click="handleViewerClick"
            @viewer-double-click="handleViewerDoubleClick"
            @controls-hover="setControlsHover"
          />

          <ImageViewer
            v-else
            :media="currentMedia"
            :image-url="imageUrl"
            :show-controls="showControls"
            :click-only-controls="clickOnlyViewerControls"
            @previous="prevMedia"
            @next="nextMedia"
            @viewer-click="handleViewerClick"
            @viewer-double-click="handleViewerDoubleClick"
            @controls-hover="setControlsHover"
          />

          <div v-if="isVideo" class="video-summary min-[1100px]:hidden shrink-0 border-t border-white/10 bg-background/95 px-4 sm:px-6 py-4">
            <div class="flex items-start justify-between gap-6 flex-wrap">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 mb-2">
                  <span class="rounded-md bg-accent/15 px-2 py-1 text-[11px] font-black text-accent">{{ mediaTypeLabel }}</span>
                  <span class="text-xs text-white/35 truncate">{{ currentMedia.relative_path }}</span>
                </div>
                <h3 class="text-xl font-black text-white truncate">{{ currentMedia.title }}</h3>
                <div class="mt-3 h-1.5 rounded-full bg-white/10 overflow-hidden">
                  <div class="h-full bg-accent transition-all" :style="{ width: `${videoProgressPercent}%` }"></div>
                </div>
              </div>

              <div class="video-summary-stats grid grid-cols-3 gap-2 text-right shrink-0 min-w-0 max-w-full">
                <div class="rounded-xl bg-white/5 border border-white/10 px-4 py-3">
                  <p class="text-[11px] text-white/35 mb-1">进度</p>
                  <p class="text-sm font-bold text-white">{{ videoProgressPercent }}%</p>
                </div>
                <div class="rounded-xl bg-white/5 border border-white/10 px-4 py-3">
                  <p class="text-[11px] text-white/35 mb-1">播放</p>
                  <p class="text-sm font-bold text-white">{{ progressText }}</p>
                </div>
                <div class="rounded-xl bg-white/5 border border-white/10 px-4 py-3">
                  <p class="text-[11px] text-white/35 mb-1">大小</p>
                  <p class="text-sm font-bold text-white">{{ formatSize(currentMedia.file_size) }}</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <button v-if="compact && showMetadataPanel" type="button" class="he-metadata-scrim" aria-label="关闭媒体信息背景" tabindex="-1" @click="toggleMetadataPanel"></button>
        <MetadataPanel
          v-if="!isFullscreen && showMetadataPanel"
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
.he-metadata-scrim { position: absolute; inset: 0; z-index: 55; background: rgba(0,0,0,.6); }
@media (max-width: 899px) {
  .he-viewer-header { flex-wrap: nowrap; padding-inline: 12px; gap: 8px; }
  .he-viewer-header h2 { width: auto; font-size: 14px; flex: 1; }
  .he-viewer-header > div { width: auto; gap: 4px; }
  .he-media-layout:not(.is-video) .he-viewer-header { flex-wrap: wrap; }
  .he-media-layout:not(.is-video) .he-viewer-header h2 { flex-basis: 100%; }
  .he-media-layout:not(.is-video) .he-viewer-header > div { width: 100%; }
  .he-viewer-header [aria-label="自动播放设置"] button span { display: none; }
  .he-media-layout.is-video > section { overflow-y: auto; }
  .he-media-layout.is-video .he-viewer-header { position: relative; opacity: 1; transform: none; pointer-events: auto; background: #060606; }
  .he-media-layout.is-video :deep(.he-video-stage) { flex: 0 0 auto; aspect-ratio: 16 / 9; width: 100%; }
  .video-summary { display: block !important; padding-bottom: calc(16px + env(safe-area-inset-bottom)); }
  .video-summary-stats { width: 100%; text-align: left; }
  .video-summary-stats > div { padding: 10px; }
  .video-summary h3 { white-space: normal; font-size: 18px; }
}
@media (max-width: 899px) and (orientation: landscape) {
  .he-media-layout.is-video :deep(.he-video-stage) { flex: 1 1 0; aspect-ratio: auto; min-height: 0; }
  .he-media-layout.is-video .video-summary { display: none !important; }
}
@media (max-height: 650px), (max-width: 640px) {
  .video-summary { display: none; }
}
</style>
