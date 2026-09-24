<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { Maximize, Minimize, Trash2, X, FileQuestion, RefreshCw, PanelRightClose, PanelRightOpen } from 'lucide-vue-next'
import { API_BASE_URL, STREAM_URL, authUrl, thumbnailUrl } from '../config'
import type { Media } from '../types'
import AudioPlayer from './media-detail/AudioPlayer.vue'
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
}>()

const emit = defineEmits<{
  close: []
  updated: [media: Media]
  navigate: [media: Media]
}>()

const currentMedia = ref<Media>(props.initialMedia)
const currentPage = ref(0)
const totalMangaPages = ref<number | null>(null)
const showMetadataPanel = ref(localStorage.getItem('he_detail_meta_panel') !== 'false')
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
const {
  isFullscreen,
  showControls,
  clickOnlyControls: clickOnlyViewerControls,
  setControlsHover,
  handleViewerClick,
  handleViewerDoubleClick,
  toggleFullscreen,
} = useMediaOverlayControls(isManga, isImage)

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

const nextMedia = () => {
  if (currentIndex.value < props.allMedia.length - 1) {
    if (isVideo.value) void saveVideoProgress(true)
    const next = props.allMedia[currentIndex.value + 1]
    currentMedia.value = next
    currentPage.value = 0
    emit('navigate', next)
  }
}

const prevMedia = () => {
  if (currentIndex.value > 0) {
    if (isVideo.value) void saveVideoProgress(true)
    const prev = props.allMedia[currentIndex.value - 1]
    currentMedia.value = prev
    currentPage.value = 0
    emit('navigate', prev)
  }
}

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
    if (media.is_missing) return
    try {
      const res = await axios.get(`${API_BASE_URL}/manga/${media.id}/pages`)
      if (currentMedia.value.id !== media.id) return
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
  const step = localStorage.getItem('he_manga_read_mode') === 'double' ? 2 : 1
  if (totalMangaPages.value === null || currentPage.value < totalMangaPages.value - 1) {
    const max = totalMangaPages.value === null ? Number.MAX_SAFE_INTEGER : totalMangaPages.value - 1
    currentPage.value = Math.min(max, currentPage.value + step)
  }
}

const prevPage = () => {
  const step = localStorage.getItem('he_manga_read_mode') === 'double' ? 2 : 1
  if (currentPage.value > 0) currentPage.value = Math.max(0, currentPage.value - step)
}

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
    <div class="fixed inset-0 z-[200] flex items-center justify-center">
      <div class="absolute inset-0 bg-background/85 backdrop-blur-2xl" @click="emit('close')"></div>

      <div class="relative w-full h-full bg-[#060606] shadow-2xl flex overflow-hidden">
        <section class="relative flex-1 min-w-0 bg-black flex flex-col">
          <header
            @mouseenter="setControlsHover(true)"
            @mouseleave="setControlsHover(false)"
            :class="showControls
              ? 'opacity-100 translate-y-0'
              : clickOnlyViewerControls
                ? 'opacity-0 -translate-y-3 pointer-events-none'
                : 'opacity-0 -translate-y-3 hover:opacity-100 hover:translate-y-0'"
            class="absolute top-0 left-0 right-0 flex items-center justify-between px-6 py-5 z-50 bg-gradient-to-b from-black/80 to-transparent transition-all duration-300"
          >
            <h2 class="text-lg font-bold truncate pr-4 grow text-white/95 drop-shadow-xl select-none">{{ currentMedia.title }}</h2>
            <div class="flex items-center gap-2">
              <button
                v-if="!isFullscreen"
                @click="toggleMetadataPanel"
                class="w-11 h-11 rounded-xl bg-black/35 backdrop-blur-md hover:bg-black/55 text-white/65 hover:text-white transition-all"
                :title="showMetadataPanel ? '收起信息侧栏' : '展开信息侧栏'"
              >
                <PanelRightClose v-if="showMetadataPanel" :size="19" class="mx-auto" />
                <PanelRightOpen v-else :size="19" class="mx-auto" />
              </button>
              <button v-if="!isVideo" @click="toggleFullscreen" class="w-11 h-11 rounded-xl bg-black/35 backdrop-blur-md hover:bg-black/55 text-white/65 hover:text-white transition-all" :title="isFullscreen ? '退出全屏' : '全屏'">
                <Minimize v-if="isFullscreen" :size="19" class="mx-auto" />
                <Maximize v-else :size="19" class="mx-auto" />
              </button>
              <button @click="emit('close')" class="w-11 h-11 rounded-xl bg-red-500/20 backdrop-blur-md hover:bg-red-500/40 text-red-100 hover:text-white transition-all" title="关闭">
                <X :size="20" class="mx-auto" />
              </button>
            </div>
          </header>

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

          <AudioPlayer v-else-if="isAudio" :media="currentMedia" :cover-url="coverUrl" />

          <MangaReader
            v-else-if="isManga"
            v-model:current-page="currentPage"
            :media="currentMedia"
            :total-pages="totalMangaPages"
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

        <MetadataPanel
          v-if="!isFullscreen && showMetadataPanel"
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
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
@media (max-height: 650px), (max-width: 640px) {
  .video-summary { display: none; }
}
</style>
