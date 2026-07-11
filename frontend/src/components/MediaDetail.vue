<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { ChevronLeft, ChevronRight, Maximize, Minimize, Plus, Star, Tag as TagIcon, Trash2, X, FileQuestion, RefreshCw } from 'lucide-vue-next'
import Artplayer from 'artplayer'
import artplayerPluginVttThumbnail from 'artplayer-plugin-vtt-thumbnail'
import { API_BASE_URL, STREAM_URL, THUMBNAIL_URL, authUrl, thumbnailUrl } from '../config'
import type { Media } from '../types'

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
const isFullscreen = ref(false)
const showControls = ref(true)
const tagInput = ref('')
const artRef = ref<HTMLDivElement | null>(null)

const isRechecking = ref(false)
const toastMessage = ref('')
const showToast = (msg: string) => {
  toastMessage.value = msg
  setTimeout(() => { toastMessage.value = '' }, 3000)
}

let controlTimer: number | undefined
let clickTimer: number | undefined
let artInstance: Artplayer | null = null
let volumeWheelElement: HTMLElement | null = null
let progressVideoElement: HTMLVideoElement | null = null
let vttBlobUrl = ''
let artInitToken = 0
let lastProgressSavedAt = 0
let lastSavedProgress = -1
let lastMangaWheelAt = 0
let mangaProgressTimer: number | undefined
let lastSavedMangaProgress = -1

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

// --- Manga thumbnail strip (virtual scroll + drag) ---
const thumbStripRef = ref<HTMLDivElement | null>(null)
const thumbStripScroll = ref(0)
const hoverThumbIndex = ref(-1)
const hoverThumbX = ref(0)
const hoverThumbY = ref(0)
let isDragging = false
let dragStartX = 0
let dragScrollStart = 0
let dragMoved = false

const THUMB_W = 110
const THUMB_H = 148
const THUMB_GAP = 12
const THUMB_PAD = 24
const THUMB_BUFFER = 5

const VOLUME_WHEEL_STEP = 0.05
const PROGRESS_SAVE_INTERVAL_MS = 5000
const MANGA_WHEEL_INTERVAL_MS = 320
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

const pageUrl = computed(() => {
  if (currentMedia.value.media_type === 'image') return authUrl(`${API_BASE_URL}/stream/${currentMedia.value.id}`)
  return authUrl(`${API_BASE_URL}/manga/${currentMedia.value.id}/page/${currentPage.value}`)
})
const videoUrl = computed(() => authUrl(`${STREAM_URL}/${currentMedia.value.id}`))
const coverUrl = computed(() => thumbnailUrl(currentMedia.value.cover_path))
const isImage = computed(() => currentMedia.value.media_type === 'image')
const isManga = computed(() => currentMedia.value.media_type === 'manga')
const isVideo = computed(() => currentMedia.value.media_type === 'video')
const isAudio = computed(() => currentMedia.value.media_type === 'audio')

// --- Audio (ASMR) state ---
// Web has no full mainstream player like the Android side; we render a basic
// HTML5 <audio> + tap-to-switch track list, enough to verify downloads and
// listen casually. Lyrics and sleep timer live only on Android for now.
interface AudioTrack { index: number; title: string; rel: string; duration: number | null; lyrics: string | null }
const audioTracks = ref<AudioTrack[]>([])
const audioCurrentIndex = ref(1)
const audioLoading = ref(false)
const audioError = ref('')
const audioElRef = ref<HTMLAudioElement | null>(null)
const audioTrackStreamUrl = computed(() =>
  authUrl(`${API_BASE_URL}/audio/${currentMedia.value.id}/track/${audioCurrentIndex.value}`),
)

const fetchAudioTracks = async () => {
  if (!isAudio.value) return
  audioLoading.value = true
  audioError.value = ''
  try {
    const res = await axios.get(`${API_BASE_URL}/audio/${currentMedia.value.id}/tracks`)
    audioTracks.value = res.data?.tracks || []
    audioCurrentIndex.value = audioTracks.value[0]?.index ?? 1
  } catch (err: any) {
    audioError.value = err.response?.data?.detail || '读取音轨失败'
    audioTracks.value = []
  } finally {
    audioLoading.value = false
  }
}

const playAudioTrack = (index: number) => {
  audioCurrentIndex.value = index
  // Source change requires a load() + play() round-trip on most browsers.
  nextTick(() => {
    const el = audioElRef.value
    if (el) {
      el.load()
      el.play().catch(() => { /* user gesture might be required; ignore */ })
    }
  })
}

const onAudioEnded = () => {
  const idx = audioTracks.value.findIndex(t => t.index === audioCurrentIndex.value)
  const next = audioTracks.value[idx + 1]
  if (next) playAudioTrack(next.index)
}
const clickOnlyViewerControls = computed(() => isFullscreen.value && (isManga.value || isImage.value))
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

const resetTimer = () => {
  if (clickOnlyViewerControls.value) return
  showControls.value = true
  window.clearTimeout(controlTimer)
  controlTimer = window.setTimeout(() => {
    showControls.value = false
  }, 1400)
}

const toggleViewerControls = () => {
  if (!clickOnlyViewerControls.value) {
    resetTimer()
    return
  }
  window.clearTimeout(controlTimer)
  if (showControls.value) {
    showControls.value = false
    return
  }
  showControls.value = true
  controlTimer = window.setTimeout(() => {
    showControls.value = false
  }, 1800)
}

const handleViewerClick = () => {
  window.clearTimeout(clickTimer)
  clickTimer = window.setTimeout(() => {
    clickTimer = undefined
    toggleViewerControls()
  }, 240)
}

const handleViewerDoubleClick = () => {
  window.clearTimeout(clickTimer)
  clickTimer = undefined
  toggleFullscreen()
}

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

const addTag = async () => {
  const name = tagInput.value.trim()
  if (!name) return
  const res = await axios.post(`${API_BASE_URL}/media/${currentMedia.value.id}/tags`, { name })
  applyMediaPatch(res.data)
  tagInput.value = ''
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

const inferredStatus = (progress: number, duration: number | null): Media['view_status'] => {
  if (!duration || progress <= 0) return progress > 0 ? 'viewing' : 'unviewed'
  if (progress / duration >= 0.95) return 'viewed'
  return 'viewing'
}

const saveVideoProgress = async (force = false, progressOverride?: number) => {
  const video = progressVideoElement
  if (!video || !isVideo.value) return

  const mediaId = currentMedia.value.id
  const progress = Math.max(0, Math.floor(progressOverride ?? (video.currentTime || 0)))
  const duration = Number.isFinite(video.duration) && video.duration > 0
    ? Math.floor(video.duration)
    : currentMedia.value.duration

  const now = Date.now()
  if (!force && now - lastProgressSavedAt < PROGRESS_SAVE_INTERVAL_MS) return
  if (!force && Math.abs(progress - lastSavedProgress) < 3) return

  lastProgressSavedAt = now
  lastSavedProgress = progress

  Object.assign(currentMedia.value, {
    progress,
    duration,
    view_status: inferredStatus(progress, duration),
  })
  emit('updated', { ...currentMedia.value })

  try {
    await updateMedia({ progress, duration: duration ?? undefined }, mediaId)
  } catch (err) {
    console.error('Failed to save video progress:', err)
  }
}

const saveMangaProgress = async (force = false) => {
  if (!isManga.value) return

  const maxPage = totalMangaPages.value ? totalMangaPages.value - 1 : currentMedia.value.page_count ? currentMedia.value.page_count - 1 : null
  const progress = maxPage === null
    ? Math.max(0, currentPage.value)
    : Math.max(0, Math.min(currentPage.value, maxPage))

  if (!force && progress === lastSavedMangaProgress) return
  lastSavedMangaProgress = progress

  Object.assign(currentMedia.value, {
    progress,
    view_status: progress > 0 ? 'viewing' : currentMedia.value.view_status,
  })
  emit('updated', { ...currentMedia.value })

  try {
    await updateMedia({ progress })
  } catch (err) {
    console.error('Failed to save manga progress:', err)
  }
}

const scheduleMangaProgressSave = () => {
  window.clearTimeout(mangaProgressTimer)
  mangaProgressTimer = window.setTimeout(() => {
    saveMangaProgress(false)
  }, 350)
}

const handleVideoLoadedMetadata = () => {
  const video = progressVideoElement
  if (!video) return

  if (currentMedia.value.progress > 0 && video.duration && currentMedia.value.progress < video.duration - 3) {
    video.currentTime = currentMedia.value.progress
  }

  saveVideoProgress(true)
}

const handleVideoEnded = () => {
  const video = progressVideoElement
  const completedAt = video && Number.isFinite(video.duration) ? video.duration : undefined

  // Artplayer has already restarted from zero in loop mode by the time this
  // listener runs. Persist completion without seeking the live video back to
  // the end, otherwise it gets trapped in an ended/replay flicker loop.
  void saveVideoProgress(true, completedAt)

  if (playMode.value === 'order') {
    nextMedia()
  } else if (playMode.value === 'shuffle') {
    if (props.allMedia && props.allMedia.length > 1) {
      let randIndex = Math.floor(Math.random() * props.allMedia.length)
      if (randIndex === currentIndex.value) {
        randIndex = (randIndex + 1) % props.allMedia.length
      }
      const next = props.allMedia[randIndex]
      currentMedia.value = next
      currentPage.value = 0
      emit('navigate', next)
    }
  }
}

const handleVideoTimeUpdate = () => {
  saveVideoProgress(false)
}

const handleVideoPause = () => {
  saveVideoProgress(true)
}

const bindVideoProgressEvents = () => {
  const video = (artInstance as unknown as { video?: HTMLVideoElement } | null)?.video
  if (!video) return

  progressVideoElement = video
  video.addEventListener('loadedmetadata', handleVideoLoadedMetadata)
  video.addEventListener('timeupdate', handleVideoTimeUpdate)
  video.addEventListener('pause', handleVideoPause)
  video.addEventListener('ended', handleVideoEnded)
}

const unbindVideoProgressEvents = () => {
  if (!progressVideoElement) return
  progressVideoElement.removeEventListener('loadedmetadata', handleVideoLoadedMetadata)
  progressVideoElement.removeEventListener('timeupdate', handleVideoTimeUpdate)
  progressVideoElement.removeEventListener('pause', handleVideoPause)
  progressVideoElement.removeEventListener('ended', handleVideoEnded)
  progressVideoElement = null
}

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

const initArtplayer = async () => {
  const token = ++artInitToken
  destroyArtplayer()
  await nextTick()

  const container = artRef.value
  if (token !== artInitToken || !container || !isVideo.value) return

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
  artInstance = new Artplayer({
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
  bindVideoProgressEvents()
}

watch(
  () => [currentMedia.value.id, currentMedia.value.media_type] as const,
  async () => {
    const newVal = currentMedia.value
    currentPage.value = newVal.media_type === 'manga' ? Math.max(0, newVal.progress || 0) : 0
    lastSavedMangaProgress = newVal.media_type === 'manga' ? currentPage.value : -1

    if (newVal.media_type === 'manga') {
      totalMangaPages.value = null
      hoverThumbIndex.value = -1
      if (!newVal.is_missing) {
        try {
          const res = await axios.get(`${API_BASE_URL}/manga/${newVal.id}/pages`)
          totalMangaPages.value = res.data.total_pages
          scrollThumbStripToPage(currentPage.value, false)
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

    if (newVal.media_type === 'audio') {
      await fetchAudioTracks()
    } else {
      audioTracks.value = []
      audioCurrentIndex.value = 1
    }
  },
  { immediate: true },
)

const getMangaPageThumbnailUrl = (pageIndex: number) => {
  return authUrl(`${API_BASE_URL}/manga/${currentMedia.value.id}/page/${pageIndex}?thumbnail=true`)
}

const jumpToPage = (pageIndex: number) => {
  currentPage.value = pageIndex
}

// --- Virtual scroll helpers ---
const thumbStripTotalWidth = computed(() => {
  if (!totalMangaPages.value) return 0
  return THUMB_PAD * 2 + totalMangaPages.value * THUMB_W + (totalMangaPages.value - 1) * THUMB_GAP
})

const visibleThumbnails = computed(() => {
  if (!totalMangaPages.value || !thumbStripRef.value) return []
  const containerW = thumbStripRef.value.clientWidth || 800
  const scrollLeft = thumbStripScroll.value
  const startIdx = Math.max(0, Math.floor((scrollLeft - THUMB_PAD) / (THUMB_W + THUMB_GAP)) - THUMB_BUFFER)
  const endIdx = Math.min(
    totalMangaPages.value - 1,
    Math.ceil((scrollLeft + containerW - THUMB_PAD) / (THUMB_W + THUMB_GAP)) + THUMB_BUFFER
  )
  const items: { index: number; left: number }[] = []
  for (let i = startIdx; i <= endIdx; i++) {
    items.push({ index: i, left: THUMB_PAD + i * (THUMB_W + THUMB_GAP) })
  }
  return items
})

const scrollThumbStripToPage = (page: number, smooth = true) => {
  nextTick(() => {
    const el = thumbStripRef.value
    if (!el) return
    const targetLeft = THUMB_PAD + page * (THUMB_W + THUMB_GAP) - el.clientWidth / 2 + THUMB_W / 2
    el.scrollTo({ left: Math.max(0, targetLeft), behavior: smooth ? 'smooth' : 'instant' })
  })
}

const onThumbStripScroll = () => {
  if (thumbStripRef.value) {
    thumbStripScroll.value = thumbStripRef.value.scrollLeft
  }
}

// --- Drag-to-scroll ---
const onThumbDragStart = (e: MouseEvent) => {
  const el = thumbStripRef.value
  if (!el) return
  isDragging = true
  dragMoved = false
  dragStartX = e.clientX
  dragScrollStart = el.scrollLeft
  el.style.cursor = 'grabbing'
  el.style.scrollBehavior = 'auto'
  window.addEventListener('mousemove', onThumbDragMove)
  window.addEventListener('mouseup', onThumbDragEnd)
}

const onThumbDragMove = (e: MouseEvent) => {
  if (!isDragging || !thumbStripRef.value) return
  const dx = e.clientX - dragStartX
  if (Math.abs(dx) > 3) dragMoved = true
  thumbStripRef.value.scrollLeft = dragScrollStart - dx
}

const onThumbDragEnd = () => {
  isDragging = false
  if (thumbStripRef.value) {
    thumbStripRef.value.style.cursor = 'grab'
    thumbStripRef.value.style.scrollBehavior = ''
  }
  window.removeEventListener('mousemove', onThumbDragMove)
  window.removeEventListener('mouseup', onThumbDragEnd)
}

const onThumbClick = (pageIndex: number) => {
  if (!dragMoved) jumpToPage(pageIndex)
}

// --- Shared hover preview ---
const onThumbMouseEnter = (pageIndex: number, e: MouseEvent) => {
  if (isDragging) return
  hoverThumbIndex.value = pageIndex
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const stripRect = thumbStripRef.value?.parentElement?.getBoundingClientRect()
  if (stripRect) {
    hoverThumbX.value = rect.left + rect.width / 2 - stripRect.left
    hoverThumbY.value = rect.top - stripRect.top - 8
  }
}

const onThumbMouseLeave = () => {
  hoverThumbIndex.value = -1
}

watch(currentPage, () => {
  if (isManga.value) {
    scheduleMangaProgressSave()
    scrollThumbStripToPage(currentPage.value)
  }
})

const nextPage = () => {
  if (totalMangaPages.value === null || currentPage.value < totalMangaPages.value - 1) {
    currentPage.value++
  }
}

const prevPage = () => {
  if (currentPage.value > 0) currentPage.value--
}

const handleMangaWheel = (e: WheelEvent) => {
  if (!isManga.value) return
  const now = Date.now()
  if (now - lastMangaWheelAt < MANGA_WHEEL_INTERVAL_MS) return

  const delta = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX
  if (Math.abs(delta) < 8) return

  e.preventDefault()
  lastMangaWheelAt = now
  if (delta > 0) {
    nextPage()
  } else {
    prevPage()
  }
}

const clearPendingLongPress = () => {
  if (longPressTimer) {
    window.clearTimeout(longPressTimer)
    longPressTimer = undefined
  }
}

const beginVideoLongPress = (direction: 'forward' | 'rewind') => {
  const video = progressVideoElement
  if (!video || longPressTimer || longPressDirection) return

  longPressTimer = window.setTimeout(() => {
    longPressTimer = undefined
    const activeVideo = progressVideoElement
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
      const rewindVideo = progressVideoElement
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

  const video = progressVideoElement
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
    } else if (isVideo.value && progressVideoElement) {
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
    } else if (isVideo.value && progressVideoElement) {
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
    if (isVideo.value && progressVideoElement) {
      e.preventDefault()
      e.stopImmediatePropagation()
      if (!finishVideoLongPress()) {
        progressVideoElement.currentTime = Math.min(
          progressVideoElement.duration || 0,
          progressVideoElement.currentTime + VIDEO_SEEK_STEP_SECONDS
        )
      }
    }
  }

  if (e.key === 'ArrowLeft') {
    if (isVideo.value && progressVideoElement) {
      e.preventDefault()
      e.stopImmediatePropagation()
      if (!finishVideoLongPress()) {
        progressVideoElement.currentTime = Math.max(
          0,
          progressVideoElement.currentTime - VIDEO_SEEK_STEP_SECONDS
        )
      }
    }
  }
}

const handleWindowBlur = () => {
  finishVideoLongPress(false)
}

const toggleFullscreen = () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}

const onFullscreenChange = () => {
  isFullscreen.value = !!document.fullscreenElement
  window.clearTimeout(controlTimer)
  showControls.value = true
  if (clickOnlyViewerControls.value) {
    controlTimer = window.setTimeout(() => {
      showControls.value = false
    }, 1800)
  }
}

onMounted(() => {
  document.body.style.overflow = 'hidden'
  window.addEventListener('keydown', handleKeydown, { capture: true })
  window.addEventListener('keyup', handleKeyup, { capture: true })
  window.addEventListener('blur', handleWindowBlur)
  window.addEventListener('mousemove', resetTimer)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  resetTimer()
})

onUnmounted(() => {
  window.clearTimeout(mangaProgressTimer)
  finishVideoLongPress(false)
  saveMangaProgress(true)
  saveVideoProgress(true)
  document.body.style.overflow = 'auto'
  window.removeEventListener('keydown', handleKeydown, { capture: true })
  window.removeEventListener('keyup', handleKeyup, { capture: true })
  window.removeEventListener('blur', handleWindowBlur)
  window.removeEventListener('mousemove', resetTimer)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  window.clearTimeout(controlTimer)
  window.clearTimeout(clickTimer)
  if (document.fullscreenElement) document.exitFullscreen()
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

          <div v-else-if="isVideo" class="relative flex-1 min-h-0 bg-black overflow-hidden">
            <div v-if="coverUrl" class="absolute inset-0 pointer-events-none" aria-hidden="true">
              <img :src="coverUrl" class="w-full h-full object-cover scale-110 blur-3xl opacity-25" alt="" />
              <div class="absolute inset-0 bg-black/60"></div>
            </div>
            <div ref="artRef" class="media-detail-player relative z-10 w-full h-full outline-none"></div>
          </div>

          <div v-else-if="isAudio" class="relative flex-1 min-h-0 bg-black overflow-hidden flex flex-col">
            <!-- Audio header: cover + meta + transport. Plain HTML5 audio is
                 enough for casual web listening; the Android app handles the
                 background playback, lyric sync, sleep timer, etc. -->
            <div class="flex items-center gap-5 px-6 py-5 border-b border-white/10 bg-gradient-to-b from-black/40 to-transparent">
              <div class="w-24 h-24 rounded-2xl bg-white/5 border border-white/10 overflow-hidden shrink-0 flex items-center justify-center">
                <img v-if="coverUrl" :src="coverUrl" class="w-full h-full object-cover" :alt="currentMedia.title" />
                <span v-else class="text-white/30 text-xs">无封面</span>
              </div>
              <div class="min-w-0 flex-1">
                <h3 class="text-xl font-black text-white truncate">{{ currentMedia.title }}</h3>
                <p class="text-xs text-white/45 mt-1 truncate">{{ currentMedia.relative_path }}</p>
                <p class="text-[11px] text-white/35 mt-1">Web 端为基础播放；歌词跟随、循环、休眠定时器请用 Android App</p>
              </div>
            </div>

            <div class="px-6 py-4 border-b border-white/10 bg-black/30">
              <div v-if="audioLoading" class="text-sm text-white/55">正在加载音轨…</div>
              <div v-else-if="audioError" class="text-sm text-red-300">{{ audioError }}</div>
              <div v-else-if="audioTracks.length === 0" class="text-sm text-white/45">没有可播放的音轨</div>
              <div v-else class="space-y-3">
                <p class="text-[11px] font-bold text-white/55 uppercase tracking-widest">
                  正在播放 · 第 {{ audioCurrentIndex }} / {{ audioTracks.length }} 轨
                </p>
                <audio
                  ref="audioElRef"
                  :src="audioTrackStreamUrl"
                  controls
                  preload="metadata"
                  class="w-full"
                  @ended="onAudioEnded"
                />
              </div>
            </div>

            <div class="flex-1 overflow-y-auto px-2 py-2">
              <button
                v-for="track in audioTracks"
                :key="track.index"
                type="button"
                @click="playAudioTrack(track.index)"
                :class="track.index === audioCurrentIndex
                  ? 'bg-accent/15 border-accent/40 text-white'
                  : 'border-white/5 text-white/70 hover:text-white hover:bg-white/[0.04]'"
                class="w-full text-left rounded-xl border px-4 py-3 mb-1.5 transition-all flex items-center gap-3"
              >
                <span class="text-xs font-mono w-7 shrink-0 text-white/55">{{ track.index.toString().padStart(2, '0') }}</span>
                <span class="flex-1 min-w-0 truncate text-sm font-bold">{{ track.title }}</span>
                <span v-if="track.lyrics" class="text-[10px] font-black text-accent/85 uppercase tracking-widest shrink-0">LRC</span>
              </button>
            </div>
          </div>

          <div v-else class="flex-1 min-h-0 flex flex-col items-center bg-black overflow-hidden relative group" @wheel="handleMangaWheel" @click="handleViewerClick" @dblclick="handleViewerDoubleClick">
            <div class="flex-1 flex items-center justify-center w-full h-full relative">
              <button
                @click.stop="isManga ? prevPage() : prevMedia()"
                :class="showControls
                  ? 'opacity-100 translate-x-0'
                  : clickOnlyViewerControls
                    ? 'opacity-0 -translate-x-6 pointer-events-none'
                    : 'opacity-0 -translate-x-6 hover:opacity-100 hover:translate-x-0'"
                class="absolute left-5 z-10 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300"
                title="上一项"
              >
                <ChevronLeft :size="34" class="mx-auto" />
              </button>

              <img
                :src="pageUrl"
                class="h-full w-full object-contain transition-opacity duration-300"
                :class="{ 'cursor-zoom-in': isImage }"
                :alt="currentMedia.title"
              />

              <button
                @click.stop="isManga ? nextPage() : nextMedia()"
                :class="showControls
                  ? 'opacity-100 translate-x-0'
                  : clickOnlyViewerControls
                    ? 'opacity-0 translate-x-6 pointer-events-none'
                    : 'opacity-0 translate-x-6 hover:opacity-100 hover:translate-x-0'"
                class="absolute right-5 z-10 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300"
                title="下一项"
              >
                <ChevronRight :size="34" class="mx-auto" />
              </button>

              <div
                v-if="isManga"
                :class="showControls || !clickOnlyViewerControls ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3 pointer-events-none'"
                class="absolute bottom-6 left-1/2 z-20 w-[min(520px,calc(100%-2rem))] -translate-x-1/2 rounded-2xl bg-black/60 backdrop-blur-md border border-white/10 px-4 py-3 shadow-2xl transition-all duration-300"
                @click.stop
              >
                <div class="flex items-center justify-between gap-4 text-sm font-mono tracking-widest">
                  <p class="text-white/70">
                    PAGE <span class="text-white/95 font-bold ml-1">{{ mangaProgressText }}</span>
                  </p>
                  <p class="font-bold text-purple-200">{{ mangaProgressPercent }}%</p>
                </div>
                <div class="mt-2 h-1.5 rounded-full bg-white/10 overflow-hidden">
                  <div class="h-full bg-purple-300 transition-all duration-300" :style="{ width: `${mangaProgressPercent}%` }"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- Manga Thumbnail Strip: Virtual Scroll + Drag -->
          <div
            v-if="isManga && totalMangaPages && totalMangaPages > 0"
            :class="[
              showControls || !clickOnlyViewerControls
                ? 'translate-y-0 opacity-100 max-h-[220px] border-t'
                : 'translate-y-full opacity-0 pointer-events-none max-h-0 overflow-hidden border-t-0'
            ]"
            class="shrink-0 border-white/10 bg-[#0c0c0e]/95 relative z-30 transition-all duration-500 ease-in-out flex flex-col"
            @click.stop
          >
            <div class="flex items-center justify-between text-xs font-semibold px-6 py-2 text-white/50">
              <span>预览目录 (共 {{ totalMangaPages }} 页)</span>
              <span>当前第 {{ currentPage + 1 }} 页</span>
            </div>

            <!-- Shared Hover Preview (single DOM element) -->
            <div
              v-if="hoverThumbIndex >= 0"
              class="absolute z-50 pointer-events-none rounded-xl border border-white/15 bg-black/95 p-1 shadow-2xl"
              :style="{
                width: '200px',
                height: '268px',
                left: `${hoverThumbX}px`,
                top: `${hoverThumbY}px`,
                transform: 'translate(-50%, -100%)',
              }"
            >
              <img
                :src="getMangaPageThumbnailUrl(hoverThumbIndex)"
                class="w-full h-full object-contain rounded-lg"
                alt="Preview"
              />
              <div class="absolute bottom-1 inset-x-1 bg-black/70 rounded-b-lg py-0.5 text-[10px] font-black text-center text-white/90">
                第 {{ hoverThumbIndex + 1 }} 页
              </div>
            </div>

            <!-- Virtual scroll container with drag -->
            <div
              ref="thumbStripRef"
              class="overflow-x-auto py-2 custom-scrollbar select-none"
              style="cursor: grab;"
              @scroll="onThumbStripScroll"
              @mousedown.prevent="onThumbDragStart"
            >
              <div :style="{ width: `${thumbStripTotalWidth}px`, height: `${THUMB_H + 4}px`, position: 'relative' }">
                <div
                  v-for="item in visibleThumbnails"
                  :key="item.index"
                  class="absolute top-0 cursor-pointer rounded-xl border-2 transition-all duration-200"
                  :class="[
                    item.index === currentPage
                      ? 'border-accent shadow-[0_0_16px_rgba(129,140,248,0.5)] bg-accent/10 scale-105 z-10'
                      : 'border-white/8 hover:border-white/25 bg-white/5'
                  ]"
                  :style="{ left: `${item.left}px`, width: `${THUMB_W}px`, height: `${THUMB_H}px` }"
                  @click="onThumbClick(item.index)"
                  @mouseenter="onThumbMouseEnter(item.index, $event)"
                  @mouseleave="onThumbMouseLeave"
                >
                  <img
                    :src="getMangaPageThumbnailUrl(item.index)"
                    loading="lazy"
                    class="w-full h-full object-cover rounded-[10px] transition-all duration-200"
                    :class="item.index === currentPage ? 'brightness-110' : 'hover:brightness-110'"
                    draggable="false"
                    alt="Page thumbnail"
                  />
                  <div
                    class="absolute bottom-0 inset-x-0 rounded-b-[10px] py-0.5 text-[10px] font-black text-center"
                    :class="item.index === currentPage ? 'bg-accent/80 text-white' : 'bg-black/60 text-white/75'"
                  >
                    {{ item.index + 1 }}
                  </div>
                </div>
              </div>
            </div>
          </div>

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

        <aside v-if="!isFullscreen" class="hidden min-[1100px]:flex w-[340px] 2xl:w-[380px] shrink-0 border-l border-white/10 bg-background/95 p-5 flex-col gap-5 overflow-y-auto custom-scrollbar">
          <div class="flex gap-4">
            <div class="w-24 h-24 rounded-xl bg-white/5 border border-white/10 overflow-hidden shrink-0">
              <img v-if="coverUrl" :src="coverUrl" class="w-full h-full object-cover" :alt="currentMedia.title" />
            </div>
            <div class="min-w-0 flex-1">
              <p class="text-xs font-bold text-white/40 uppercase tracking-widest mb-2">媒体信息</p>
              <h3 class="text-xl font-black text-white leading-snug break-words">{{ currentMedia.title }}</h3>
              <p class="mt-2 text-xs text-white/40 break-all line-clamp-2">{{ currentMedia.relative_path }}</p>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-2 text-sm">
            <div class="rounded-xl bg-white/5 p-3 border border-white/10">
              <p class="text-white/35 text-xs mb-1">类型</p>
              <p class="font-semibold">{{ mediaTypeLabel }}</p>
            </div>
            <div class="rounded-xl bg-white/5 p-3 border border-white/10">
              <p class="text-white/35 text-xs mb-1">进度</p>
              <p class="font-semibold">{{ isVideo ? `${videoProgressPercent}%` : isManga ? `${mangaProgressPercent}%` : '-' }}</p>
            </div>
            <div class="rounded-xl bg-white/5 p-3 border border-white/10">
              <p class="text-white/35 text-xs mb-1">时长/页数</p>
              <p class="font-semibold">{{ isVideo ? formatDuration(currentMedia.duration) : isManga ? progressText : (currentMedia.page_count || '-') }}</p>
            </div>
            <div class="rounded-xl bg-white/5 p-3 border border-white/10">
              <p class="text-white/35 text-xs mb-1">尺寸</p>
              <p class="font-semibold">{{ currentMedia.width && currentMedia.height ? `${currentMedia.width} x ${currentMedia.height}` : '-' }}</p>
            </div>
          </div>

          <div v-if="isVideo" class="rounded-xl border border-white/8 bg-white/[0.025] px-3.5 py-3 text-[11px] leading-relaxed text-white/45">
            <p class="font-bold text-white/65 mb-1.5">快捷播放</p>
            <p><kbd class="text-white/75">←</kbd> / <kbd class="text-white/75">→</kbd> 短按跳转 10 秒，长按快退 / 2× 快进</p>
          </div>

          <div v-if="isManga && mangaPageTotal" class="rounded-2xl bg-white/5 border border-white/10 p-4">
            <div class="flex items-center justify-between text-sm">
              <span class="font-bold text-white/75">阅读进度</span>
              <span class="font-mono font-bold text-purple-200">{{ progressText }}</span>
            </div>
            <div class="mt-3 h-1.5 rounded-full bg-white/10 overflow-hidden">
              <div class="h-full bg-purple-300 transition-all duration-300" :style="{ width: `${mangaProgressPercent}%` }"></div>
            </div>
          </div>

          <button
            type="button"
            @click="updateMedia({ favorite: !currentMedia.favorite })"
            :class="currentMedia.favorite ? 'bg-amber-400 text-black' : 'bg-white/5 text-white/70 hover:text-white'"
            class="w-full h-11 rounded-xl border border-white/10 font-bold flex items-center justify-center gap-2 transition-all"
          >
            <Star :size="17" :fill="currentMedia.favorite ? 'currentColor' : 'none'" />
            {{ currentMedia.favorite ? '已收藏' : '收藏' }}
          </button>

          <div>
            <p class="text-xs font-bold text-white/40 uppercase tracking-widest mb-2">评分</p>
            <div class="flex gap-2">
              <button
                v-for="score in 5"
                :key="score"
                type="button"
                @click.stop="setRating(score)"
                class="w-10 h-10 rounded-xl bg-white/5 hover:bg-white/10 transition-all text-amber-300 cursor-pointer"
                :title="`${score} 星`"
              >
                <Star :size="20" class="mx-auto" :fill="currentMedia.rating >= score ? 'currentColor' : 'none'" />
              </button>
            </div>
          </div>

          <div>
            <div class="flex items-center gap-2 text-xs font-bold text-white/40 uppercase tracking-widest mb-2">
              <TagIcon :size="14" />
              <span>标签</span>
            </div>
            <div class="flex flex-wrap gap-2 mb-3">
              <span v-for="tag in currentMedia.tags" :key="tag.id" class="inline-flex items-center gap-1 rounded-lg bg-white/8 border border-white/10 px-2 py-1 text-xs">
                {{ tag.name }}
                <button type="button" @click="removeTag(tag.id)" class="text-white/35 hover:text-red-300" title="移除标签">
                  <Trash2 :size="12" />
                </button>
              </span>
              <span v-if="currentMedia.tags.length === 0" class="text-sm text-white/35">还没有标签</span>
            </div>
            <div class="flex gap-2">
              <input
                v-model="tagInput"
                @keydown.enter="addTag"
                class="min-w-0 flex-1 rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-accent/50"
                placeholder="添加标签"
              />
              <button type="button" @click="addTag" class="w-10 rounded-xl bg-accent text-white flex items-center justify-center" title="添加标签">
                <Plus :size="18" />
              </button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  </Teleport>
</template>

<style>
.media-detail-player .art-video-player {
  background-color: transparent !important;
}
</style>
