<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { Maximize, Minimize, Trash2, X, FileQuestion, RefreshCw } from 'lucide-vue-next'
import type Artplayer from 'artplayer'
import { API_BASE_URL, STREAM_URL, THUMBNAIL_URL, authUrl, thumbnailUrl } from '../config'
import type { Media } from '../types'
import AudioPlayer from './media-detail/AudioPlayer.vue'
import ImageViewer from './media-detail/ImageViewer.vue'
import MangaReader from './media-detail/MangaReader.vue'
import MetadataPanel from './media-detail/MetadataPanel.vue'
import VideoPlayer from './media-detail/VideoPlayer.vue'
import { useMediaOverlayControls } from '../composables/useMediaOverlayControls'
import { useMediaProgress } from '../composables/useMediaProgress'
import { useMediaKeyboard } from '../composables/useMediaKeyboard'

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
const artRef = ref<HTMLDivElement | null>(null)

const isRechecking = ref(false)
const toastMessage = ref('')
const showToast = (msg: string) => {
  toastMessage.value = msg
  setTimeout(() => { toastMessage.value = '' }, 3000)
}

let clickTimer: number | undefined
let artInstance: Artplayer | null = null
let volumeWheelElement: HTMLElement | null = null
let vttBlobUrl = ''
let artInitToken = 0

let longPressTimer: number | undefined
let longPressDirection: 'forward' | 'rewind' | null = null
let originalPlaybackRate = 1
let rewindInterval: number | undefined
let rewoundSeconds = 0

const VIDEO_SEEK_STEP_SECONDS = 10
const LONG_PRESS_DELAY_MS = 400
const REWIND_REPEAT_INTERVAL_MS = 250

// --- Play Mode Configuration ---
type PlayMode = 'stop' | 'loop' | 'order' | 'shuffle'

const PLAY_MODES: PlayMode[] = ['stop', 'loop', 'order', 'shuffle']
const PLAY_MODE_LABELS: Record<PlayMode, string> = {
  stop: '播放完暂停',
  loop: '单片循环',
  order: '顺序播放',
  shuffle: '随机播放',
}

const savedPlayMode = localStorage.getItem('he_play_mode') as PlayMode | null
const playMode = ref<PlayMode>(savedPlayMode && PLAY_MODES.includes(savedPlayMode) ? savedPlayMode : 'stop')

const togglePlayMode = () => {
  const idx = PLAY_MODES.indexOf(playMode.value)
  const nextMode = PLAY_MODES[(idx + 1) % PLAY_MODES.length]
  playMode.value = nextMode
  localStorage.setItem('he_play_mode', nextMode)
  if (artInstance) {
    artInstance.option.loop = nextMode === 'loop'
  }
}

const playModeLabel = computed(() => PLAY_MODE_LABELS[playMode.value])

const getPlayModeIconHtml = (mode: PlayMode) => {
  let icon = ''
  if (mode === 'loop') {
    icon = '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/><path d="M11 10h1v4"/>'
  } else if (mode === 'order') {
    icon = '<path d="M4 6h8"/><path d="M4 12h5"/><path d="M4 18h8"/><path d="m15 9 5 3-5 3Z"/>'
  } else if (mode === 'shuffle') {
    icon = '<path d="M3 6h3c5 0 5 12 10 12h5"/><path d="m18 15 3 3-3 3"/><path d="M3 18h3c2.1 0 3.3-2.1 4.5-4.5"/><path d="M13.5 8.5C14.7 6.6 16 6 18 6h3"/><path d="m18 3 3 3-3 3"/>'
  } else {
    icon = '<rect x="7" y="7" width="10" height="10" rx="2"/>'
  }

  return `<span data-play-mode="${mode}" aria-hidden="true" style="display:flex;align-items:center;justify-content:center;width:22px;height:22px;color:inherit"><svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${icon}</svg></span>`
}

const updatePlayModeControl = (control: HTMLElement) => {
  control.innerHTML = getPlayModeIconHtml(playMode.value)
  // Artplayer's tooltip is rendered from aria-label (hint.css), not title/data-tooltip.
  control.setAttribute('aria-label', playModeLabel.value)
  control.setAttribute('title', playModeLabel.value)
}

const VOLUME_WHEEL_STEP = 0.05
const VOLUME_WHEEL_SELECTOR = [
  '.art-control-volume',
  '.art-volume-panel',
  '.art-volume-inner',
  '.art-volume-slider',
  '.art-volume-handle',
  '.art-volume-loaded',
  '.art-volume-indicator',
  '.art-icon-volume',
  '.art-icon-volumeClose',
].join(', ')
const VOLUME_WHEEL_HOVER_SELECTOR = VOLUME_WHEEL_SELECTOR
  .split(', ')
  .map(selector => `${selector}:hover`)
  .join(', ')

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
    applyMediaPatch(res.data)
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
    const next = props.allMedia[currentIndex.value + 1]
    currentMedia.value = next
    currentPage.value = 0
    emit('navigate', next)
  }
}

const prevMedia = () => {
  if (currentIndex.value > 0) {
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

const isArtVolumeTarget = (e: WheelEvent) => {
  const path = e.composedPath()
  const isVolumePath = path.some(node => node instanceof Element && !!node.closest(VOLUME_WHEEL_SELECTOR))
  if (isVolumePath) return true
  return !!volumeWheelElement?.querySelector(VOLUME_WHEEL_HOVER_SELECTOR)
}

const handleVolumeWheel = (e: WheelEvent) => {
  if (!artInstance || !isArtVolumeTarget(e)) return
  e.preventDefault()
  e.stopPropagation()

  const delta = e.deltaY || e.deltaX
  const direction = delta < 0 ? 1 : -1
  const currentVolume = artInstance.muted ? 0 : artInstance.volume
  const nextVolume = Math.min(1, Math.max(0, currentVolume + direction * VOLUME_WHEEL_STEP))

  artInstance.muted = nextVolume === 0
  artInstance.volume = Number(nextVolume.toFixed(2))
}

const interceptClick = (e: MouseEvent) => {
  const target = e.target as HTMLElement
  if (target.tagName.toLowerCase() !== 'video' && !target.classList.contains('art-state')) return

  e.stopPropagation()
  e.stopImmediatePropagation()
  e.preventDefault()

  if (e.type === 'dblclick') {
    window.clearTimeout(clickTimer)
    clickTimer = undefined
    if (artInstance) artInstance.fullscreen = !artInstance.fullscreen
    return
  }

  if (clickTimer) {
    window.clearTimeout(clickTimer)
    clickTimer = undefined
  } else {
    clickTimer = window.setTimeout(() => {
      clickTimer = undefined
      if (artInstance) artInstance.toggle()
    }, 300)
  }
}

const handleVideoSequenceEnded = () => {
  if (playMode.value === 'order') {
    nextMedia()
  } else if (playMode.value === 'shuffle' && props.allMedia.length > 1) {
    let randomIndex = Math.floor(Math.random() * props.allMedia.length)
    if (randomIndex === currentIndex.value) randomIndex = (randomIndex + 1) % props.allMedia.length
    const next = props.allMedia[randomIndex]
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

const destroyArtplayer = () => {
  unbindVideoProgressEvents()
  volumeWheelElement?.removeEventListener('wheel', handleVolumeWheel, { capture: true })
  artRef.value?.removeEventListener('click', interceptClick, true)
  artRef.value?.removeEventListener('dblclick', interceptClick, true)

  if (artInstance) {
    try {
      artInstance.destroy(false)
    } catch (err) {
      console.warn('Artplayer destroy failed:', err)
    }
    artInstance = null
  }

  if (vttBlobUrl) {
    URL.revokeObjectURL(vttBlobUrl)
    vttBlobUrl = ''
  }

  volumeWheelElement = null
  artRef.value?.replaceChildren()
}

const stopArtplayer = () => {
  artInitToken++
  destroyArtplayer()
}

const setArtContainer = (container: HTMLDivElement | null) => {
  artRef.value = container
}

const initArtplayer = async () => {
  const token = ++artInitToken
  destroyArtplayer()
  await nextTick()

  const container = artRef.value
  if (token !== artInitToken || !container || !isVideo.value) return

  let artplayerModule: typeof import('artplayer')
  let vttPluginModule: typeof import('artplayer-plugin-vtt-thumbnail')
  try {
    const loadedModules = await Promise.all([
      import('artplayer'),
      import('artplayer-plugin-vtt-thumbnail'),
    ])
    artplayerModule = loadedModules[0]
    vttPluginModule = loadedModules[1]
  } catch (err) {
    console.error('Failed to load video player:', err)
    showToast('播放器加载失败，请重试')
    return
  }
  if (token !== artInitToken) return

  const ArtplayerConstructor = artplayerModule.default
  const artplayerPluginVttThumbnail = vttPluginModule.default
  const plugins = []
  if (currentMedia.value.cover_path) {
    try {
      const vttRoute = `${API_BASE_URL}/thumbnails/${currentMedia.value.cover_path.replace('.jpg', '.vtt')}`
      const res = await axios.get(vttRoute)
      const text = String(res.data).replace(
        /(?:\/thumbnails\/)?([^\s#]+\.jpg)(#xywh=[0-9,]+)?/g,
        (_match, file, xywh = '') => `${authUrl(`${THUMBNAIL_URL}/${file}`)}${xywh}`,
      )
      const blob = new Blob([text], { type: 'text/vtt' })
      const nextVttBlobUrl = URL.createObjectURL(blob)

      if (token !== artInitToken) {
        URL.revokeObjectURL(nextVttBlobUrl)
        return
      }

      vttBlobUrl = nextVttBlobUrl
      plugins.push(artplayerPluginVttThumbnail({ vtt: vttBlobUrl }))
    } catch {
      console.log('VTT thumbnail not available for this video.')
    }
  }

  if (token !== artInitToken) return

  container.replaceChildren()
  artInstance = new ArtplayerConstructor({
    container,
    url: videoUrl.value,
    volume: 0.5,
    autoplay: true,
    loop: playMode.value === 'loop',
    pip: true,
    autoSize: true,
    autoMini: true,
    screenshot: true,
    setting: true,
    playbackRate: true,
    aspectRatio: true,
    fullscreen: true,
    fullscreenWeb: true,
    miniProgressBar: true,
    mutex: true,
    backdrop: true,
    playsInline: true,
    autoPlayback: true,
    airplay: true,
    theme: '#818cf8',
    controls: [
      {
        name: 'playMode',
        position: 'right',
        index: 10,
        html: getPlayModeIconHtml(playMode.value),
        tooltip: playModeLabel.value,
        click: function (art: any, event: Event) {
          togglePlayMode()
          const btnEl = event.currentTarget as HTMLElement | null
          if (btnEl) {
            updatePlayModeControl(btnEl)
          }
          art.notice.show = `播放模式: ${playModeLabel.value}`
        }
      }
    ],
    plugins,
  })

  container.addEventListener('click', interceptClick, true)
  container.addEventListener('dblclick', interceptClick, true)
  volumeWheelElement = container.querySelector('.art-video-player') ?? container
  volumeWheelElement.addEventListener('wheel', handleVolumeWheel, { capture: true, passive: false })
  bindVideoProgressEvents((artInstance as unknown as { video?: HTMLVideoElement } | null)?.video)
}

watch(
  () => [currentMedia.value.id, currentMedia.value.media_type] as const,
  async () => {
    const newVal = currentMedia.value
    currentPage.value = newVal.media_type === 'manga' ? Math.max(0, newVal.progress || 0) : 0

    if (newVal.media_type === 'manga') {
      totalMangaPages.value = null
      if (!newVal.is_missing) {
        try {
          const res = await axios.get(`${API_BASE_URL}/manga/${newVal.id}/pages`)
          totalMangaPages.value = res.data.total_pages
          // Trigger batch thumbnail generation in background
          axios.post(`${API_BASE_URL}/manga/${newVal.id}/thumbnails/generate`).catch(() => {})
        } catch {
          totalMangaPages.value = null
        }
      }
    }

    if (newVal.media_type === 'video' && !newVal.is_missing) {
      await initArtplayer()
    } else {
      stopArtplayer()
    }

  },
  { immediate: true },
)

const nextPage = () => {
  if (totalMangaPages.value === null || currentPage.value < totalMangaPages.value - 1) currentPage.value++
}

const prevPage = () => {
  if (currentPage.value > 0) currentPage.value--
}

const clearPendingLongPress = () => {
  if (longPressTimer) {
    window.clearTimeout(longPressTimer)
    longPressTimer = undefined
  }
}

const beginVideoLongPress = (direction: 'forward' | 'rewind') => {
  const video = progressVideoElement.value
  if (!video || longPressTimer || longPressDirection) return

  longPressTimer = window.setTimeout(() => {
    longPressTimer = undefined
    const activeVideo = progressVideoElement.value
    if (!activeVideo) return

    longPressDirection = direction
    if (direction === 'forward') {
      originalPlaybackRate = activeVideo.playbackRate || 1
      activeVideo.playbackRate = 2
      if (artInstance) artInstance.notice.show = '2.0x 快进中'
      return
    }

    // Douyin-style rewind: keep the current play/pause state and repeatedly
    // jump backward in fixed chunks instead of simulating reverse playback.
    rewoundSeconds = 0
    const rewindOneStep = () => {
      const rewindVideo = progressVideoElement.value
      if (!rewindVideo || longPressDirection !== 'rewind') return true

      const previousTime = rewindVideo.currentTime
      const nextTime = Math.max(0, previousTime - VIDEO_SEEK_STEP_SECONDS)
      rewindVideo.currentTime = nextTime
      rewoundSeconds += previousTime - nextTime

      if (artInstance) {
        artInstance.notice.show = `连续快退 ${Math.round(rewoundSeconds)} 秒`
      }
      return nextTime === 0
    }

    if (!rewindOneStep()) {
      rewindInterval = window.setInterval(() => {
        if (rewindOneStep() && rewindInterval) {
          window.clearInterval(rewindInterval)
          rewindInterval = undefined
        }
      }, REWIND_REPEAT_INTERVAL_MS)
    }
  }, LONG_PRESS_DELAY_MS)
}

const finishVideoLongPress = (showNotice = true) => {
  clearPendingLongPress()

  const video = progressVideoElement.value
  const direction = longPressDirection
  if (!direction) return false

  if (direction === 'forward' && video) {
    video.playbackRate = originalPlaybackRate
    if (showNotice && artInstance) {
      artInstance.notice.show = `恢复播放 (${originalPlaybackRate}x)`
    }
  }

  if (direction === 'rewind') {
    if (rewindInterval) {
      window.clearInterval(rewindInterval)
      rewindInterval = undefined
    }
    if (video) {
      void saveVideoProgress(true)
      if (showNotice && artInstance) {
        artInstance.notice.show = `已快退 ${Math.round(rewoundSeconds)} 秒`
      }
    }
  }

  longPressDirection = null
  return true
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
      if (!finishVideoLongPress()) {
        progressVideoElement.value.currentTime = Math.min(
          progressVideoElement.value.duration || 0,
          progressVideoElement.value.currentTime + VIDEO_SEEK_STEP_SECONDS
        )
      }
    }
  }

  if (e.key === 'ArrowLeft') {
    if (isVideo.value && progressVideoElement.value) {
      e.preventDefault()
      e.stopImmediatePropagation()
      if (!finishVideoLongPress()) {
        progressVideoElement.value.currentTime = Math.max(
          0,
          progressVideoElement.value.currentTime - VIDEO_SEEK_STEP_SECONDS
        )
      }
    }
  }
}

const handleWindowBlur = () => {
  finishVideoLongPress(false)
}

useMediaKeyboard(handleKeydown, handleKeyup, handleWindowBlur)

onUnmounted(() => {
  finishVideoLongPress(false)
  window.clearTimeout(clickTimer)
  stopArtplayer()
})
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[200] flex items-center justify-center">
      <div class="absolute inset-0 bg-background/85 backdrop-blur-2xl" @click="emit('close')"></div>

      <div class="relative w-full h-full bg-[#060606] shadow-2xl flex overflow-hidden">
        <section class="relative flex-1 min-w-0 bg-black flex flex-col">
          <header
            :class="showControls
              ? 'opacity-100 translate-y-0'
              : clickOnlyViewerControls
                ? 'opacity-0 -translate-y-3 pointer-events-none'
                : 'opacity-0 -translate-y-3 hover:opacity-100 hover:translate-y-0'"
            class="absolute top-0 left-0 right-0 flex items-center justify-between px-6 py-5 z-50 bg-gradient-to-b from-black/80 to-transparent transition-all duration-300"
          >
            <h2 class="text-lg font-bold truncate pr-4 grow text-white/95 drop-shadow-xl select-none">{{ currentMedia.title }}</h2>
            <div class="flex items-center gap-2">
              <button @click="toggleFullscreen" class="w-11 h-11 rounded-xl bg-black/35 backdrop-blur-md hover:bg-black/55 text-white/65 hover:text-white transition-all" :title="isFullscreen ? '退出全屏' : '全屏'">
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
          />

          <div v-if="isVideo" class="min-[1100px]:hidden shrink-0 border-t border-white/10 bg-background/95 px-4 sm:px-6 py-4">
            <div class="flex items-start justify-between gap-6">
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

              <div class="grid grid-cols-3 gap-2 text-right shrink-0 min-w-[300px]">
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
          v-if="!isFullscreen"
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
