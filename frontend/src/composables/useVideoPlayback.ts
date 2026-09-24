import { computed, nextTick, onUnmounted, ref, watch, type ComputedRef, type Ref } from 'vue'
import axios from 'axios'
import type Artplayer from 'artplayer'
import { API_BASE_URL, THUMBNAIL_URL, authUrl } from '../config'
import type { Media } from '../types'

interface VideoPlaybackOptions {
  media: Ref<Media>
  isVideo: ComputedRef<boolean>
  videoUrl: ComputedRef<string>
  videoElement: Ref<HTMLVideoElement | null>
  bindVideo: (video: HTMLVideoElement | null | undefined) => void
  unbindVideo: () => void
  saveProgress: (force?: boolean) => Promise<void>
  onError: (message: string) => void
}

/** Owns the Artplayer instance, VTT, pointer and keyboard playback interactions. */
export function useVideoPlayback(options: VideoPlaybackOptions) {
  const artRef = ref<HTMLDivElement | null>(null)
  let clickTimer: number | undefined
  let artInstance: Artplayer | null = null
  let volumeWheelElement: HTMLElement | null = null
  let vttBlobUrl = ''
  let artInitToken = 0
  let activeMediaId = 0
  let containerResizeObserver: ResizeObserver | null = null

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
    artInstance.notice.show = `音量: ${Math.round(artInstance.volume * 100)}%`
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

  const destroyArtplayer = () => {
    containerResizeObserver?.disconnect()
    containerResizeObserver = null
    clearPendingLongPress()
    if (longPressDirection === 'forward' && options.videoElement.value) {
      options.videoElement.value.playbackRate = originalPlaybackRate
    }
    if (rewindInterval) window.clearInterval(rewindInterval)
    rewindInterval = undefined
    longPressDirection = null
    options.unbindVideo()
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

  const loadVttThumbnail = async (token: number, coverPath: string, player: Artplayer) => {
    try {
      const [{ default: plugin }, res] = await Promise.all([
        import('artplayer-plugin-vtt-thumbnail'),
        axios.get(`${API_BASE_URL}/thumbnails/${coverPath.replace('.jpg', '.vtt')}`),
      ])
      if (token !== artInitToken || artInstance !== player) return
      const content = String(res.data).replace(
        /(?:\/thumbnails\/)?([^\s#]+\.jpg)(#xywh=[0-9,]+)?/g,
        (_match, file, xywh = '') => `${authUrl(`${THUMBNAIL_URL}/${file}`)}${xywh}`,
      )
      const blobUrl = URL.createObjectURL(new Blob([content], { type: 'text/vtt' }))
      if (token !== artInitToken || artInstance !== player) {
        URL.revokeObjectURL(blobUrl)
        return
      }
      vttBlobUrl = blobUrl
    await player.plugins.add(plugin({ vtt: blobUrl }))
    } catch {
      // Thumbnails are optional; playback has already started.
    }
  }

  const initArtplayer = async () => {
    const token = ++artInitToken
    destroyArtplayer()
    await nextTick()

    const container = artRef.value
    if (token !== artInitToken || !container || !options.isVideo.value) return

    let artplayerModule: typeof import('artplayer')
    try {
      artplayerModule = await import('artplayer')
    } catch (err) {
      console.error('Failed to load video player:', err)
      options.onError('播放器加载失败，请重试')
      return
    }
    if (token !== artInitToken) return

    const ArtplayerConstructor = artplayerModule.default
    if (token !== artInitToken) return

    container.replaceChildren()
    artInstance = new ArtplayerConstructor({
      container,
      url: options.videoUrl.value,
      volume: 0.5,
      autoplay: true,
      loop: playMode.value === 'loop',
      pip: true,
      autoSize: false,
      autoMini: true,
      screenshot: true,
      setting: true,
      playbackRate: true,
      aspectRatio: true,
      fullscreen: true,
      fullscreenWeb: false,
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
    })

    container.addEventListener('click', interceptClick, true)
    container.addEventListener('dblclick', interceptClick, true)
    volumeWheelElement = container.querySelector('.art-video-player') ?? container
    volumeWheelElement.addEventListener('wheel', handleVolumeWheel, { capture: true, passive: false })
    activeMediaId = options.media.value.id
    options.bindVideo((artInstance as unknown as { video?: HTMLVideoElement } | null)?.video)
    if (options.media.value.cover_path) void loadVttThumbnail(token, options.media.value.cover_path, artInstance)
    containerResizeObserver = new ResizeObserver(() => {
      if (artInstance && typeof (artInstance as unknown as { resize?: () => void }).resize === 'function') {
        (artInstance as unknown as { resize: () => void }).resize()
      }
    })
    containerResizeObserver.observe(container)
  }
  const clearPendingLongPress = () => {
    if (longPressTimer) {
      window.clearTimeout(longPressTimer)
      longPressTimer = undefined
    }
  }

  const beginVideoLongPress = (direction: 'forward' | 'rewind') => {
    const video = options.videoElement.value
    if (!video || longPressTimer || longPressDirection) return

    longPressTimer = window.setTimeout(() => {
      longPressTimer = undefined
      const activeVideo = options.videoElement.value
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
        const rewindVideo = options.videoElement.value
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

    const video = options.videoElement.value
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
      if (video && activeMediaId === options.media.value.id) {
        void options.saveProgress(true)
        if (showNotice && artInstance) {
          artInstance.notice.show = `已快退 ${Math.round(rewoundSeconds)} 秒`
        }
      }
    }

    longPressDirection = null
    return true
  }


  watch(() => [options.media.value.id, options.media.value.media_type, options.media.value.is_missing] as const, () => {
    stopArtplayer()
    if (options.isVideo.value && !options.media.value.is_missing) void initArtplayer()
  }, { immediate: true, flush: 'sync' })

  onUnmounted(() => {
    finishVideoLongPress(false)
    window.clearTimeout(clickTimer)
    stopArtplayer()
  })

  return {
    playMode,
    setArtContainer,
    beginVideoLongPress,
    finishVideoLongPress,
    seekVideo: (direction: 'forward' | 'rewind') => {
      if (finishVideoLongPress()) return
      const video = options.videoElement.value
      if (!video) return
      video.currentTime = direction === 'forward'
        ? Math.min(video.duration || 0, video.currentTime + VIDEO_SEEK_STEP_SECONDS)
        : Math.max(0, video.currentTime - VIDEO_SEEK_STEP_SECONDS)
      if (artInstance) artInstance.notice.show = `${direction === 'forward' ? '快进' : '快退'} ${VIDEO_SEEK_STEP_SECONDS} 秒`
    },
    isArtFullscreen: () => !!artInstance?.fullscreen,
    exitArtFullscreen: () => { if (artInstance) artInstance.fullscreen = false },
    resizeVideoPlayer: () => {
      if (artInstance && typeof (artInstance as unknown as { resize?: () => void }).resize === 'function') {
        (artInstance as unknown as { resize: () => void }).resize()
      }
    },
  }
}
