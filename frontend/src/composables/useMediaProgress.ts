import { onUnmounted, ref, watch, type ComputedRef, type Ref } from 'vue'
import type { Media } from '../types'

type ProgressPatch = Partial<Pick<Media, 'duration' | 'progress'>>

interface MediaProgressOptions {
  media: Ref<Media>
  currentPage: Ref<number>
  totalMangaPages: Ref<number | null>
  isVideo: ComputedRef<boolean>
  isManga: ComputedRef<boolean>
  updateMedia: (payload: ProgressPatch, mediaId?: number) => Promise<void>
  emitUpdated: (media: Media) => void
  onVideoEnded: () => void
}

/** Owns throttled video/manga progress persistence and media event binding. */
export function useMediaProgress(options: MediaProgressOptions) {
  const videoElement = ref<HTMLVideoElement | null>(null)
  let lastVideoSavedAt = 0
  let lastVideoProgress = -1
  let lastMangaProgress = -1
  let mangaTimer: number | undefined
  const SAVE_INTERVAL_MS = 5000

  const inferredStatus = (progress: number, duration: number | null): Media['view_status'] => {
    if (!duration || progress <= 0) return progress > 0 ? 'viewing' : 'unviewed'
    return progress / duration >= 0.95 ? 'viewed' : 'viewing'
  }

  const saveVideoProgress = async (force = false, progressOverride?: number) => {
    const video = videoElement.value
    if (!video || !options.isVideo.value) return
    const mediaId = options.media.value.id
    const progress = Math.max(0, Math.floor(progressOverride ?? (video.currentTime || 0)))
    const duration = Number.isFinite(video.duration) && video.duration > 0
      ? Math.floor(video.duration)
      : options.media.value.duration
    const now = Date.now()
    if (!force && now - lastVideoSavedAt < SAVE_INTERVAL_MS) return
    if (!force && Math.abs(progress - lastVideoProgress) < 3) return
    lastVideoSavedAt = now
    lastVideoProgress = progress

    Object.assign(options.media.value, { progress, duration, view_status: inferredStatus(progress, duration) })
    options.emitUpdated({ ...options.media.value })
    try {
      await options.updateMedia({ progress, duration: duration ?? undefined }, mediaId)
    } catch (err) {
      console.error('Failed to save video progress:', err)
    }
  }

  const saveMangaProgress = async (force = false) => {
    if (!options.isManga.value) return
    const media = options.media.value
    const maxPage = options.totalMangaPages.value
      ? options.totalMangaPages.value - 1
      : media.page_count ? media.page_count - 1 : null
    const progress = maxPage === null
      ? Math.max(0, options.currentPage.value)
      : Math.max(0, Math.min(options.currentPage.value, maxPage))
    if (!force && progress === lastMangaProgress) return
    lastMangaProgress = progress

    Object.assign(media, { progress, view_status: progress > 0 ? 'viewing' : media.view_status })
    options.emitUpdated({ ...media })
    try {
      await options.updateMedia({ progress })
    } catch (err) {
      console.error('Failed to save manga progress:', err)
    }
  }

  const scheduleMangaProgressSave = () => {
    window.clearTimeout(mangaTimer)
    mangaTimer = window.setTimeout(() => { void saveMangaProgress(false) }, 350)
  }

  const onLoadedMetadata = () => {
    const video = videoElement.value
    if (!video) return
    if (options.media.value.progress > 0 && video.duration && options.media.value.progress < video.duration - 3) {
      video.currentTime = options.media.value.progress
    }
    void saveVideoProgress(true)
  }
  const onTimeUpdate = () => { void saveVideoProgress(false) }
  const onPause = () => { void saveVideoProgress(true) }
  const onEnded = () => {
    const video = videoElement.value
    const completedAt = video && Number.isFinite(video.duration) ? video.duration : undefined
    void saveVideoProgress(true, completedAt)
    options.onVideoEnded()
  }

  const unbindVideo = () => {
    const video = videoElement.value
    if (!video) return
    video.removeEventListener('loadedmetadata', onLoadedMetadata)
    video.removeEventListener('timeupdate', onTimeUpdate)
    video.removeEventListener('pause', onPause)
    video.removeEventListener('ended', onEnded)
    videoElement.value = null
  }

  const bindVideo = (video: HTMLVideoElement | null | undefined) => {
    unbindVideo()
    if (!video) return
    videoElement.value = video
    video.addEventListener('loadedmetadata', onLoadedMetadata)
    video.addEventListener('timeupdate', onTimeUpdate)
    video.addEventListener('pause', onPause)
    video.addEventListener('ended', onEnded)
  }

  watch(() => options.media.value.id, () => {
    lastVideoSavedAt = 0
    lastVideoProgress = -1
    // MediaDetail applies the persisted manga page in its own id watcher.
    // Defer this baseline until those synchronous watchers have run.
    queueMicrotask(() => {
      lastMangaProgress = options.isManga.value ? options.currentPage.value : -1
    })
  })
  watch(options.currentPage, () => {
    if (options.isManga.value) scheduleMangaProgressSave()
  })

  onUnmounted(() => {
    window.clearTimeout(mangaTimer)
    void saveMangaProgress(true)
    void saveVideoProgress(true)
    unbindVideo()
  })

  return {
    videoElement,
    bindVideo,
    unbindVideo,
    saveVideoProgress,
  }
}
