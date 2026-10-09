<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import {
  FileText,
  Music,
  Pause,
  Play,
  Repeat,
  Repeat1,
  RotateCcw,
  RotateCw,
  Shuffle,
  SkipBack,
  SkipForward,
  Volume1,
  Volume2,
  VolumeX,
} from 'lucide-vue-next'
import { API_BASE_URL, authUrl } from '../../config'
import type { Media } from '../../types'
import { audioPlaybackStore } from '../../stores/audioPlaybackStore'

interface AudioTrack {
  index: number
  title: string
  rel: string
  duration: number | null
  lyrics: string | null
}

interface LyricLine {
  t: number
  text: string
}

type LoopMode = 'list' | 'single' | 'shuffle' | 'off'

const props = defineProps<{
  media: Media
  coverUrl: string
}>()

const tracks = ref<AudioTrack[]>([])
const currentIndex = ref(1)
const loading = ref(false)
const error = ref('')
const audioRef = ref<HTMLAudioElement | null>(null)
let requestId = 0
let lyricsRequestId = 0
let resumeTime = 0
let lastSavedAt = 0
const playbackError = ref('')
let playingMediaId = props.media.id
const resumeKey = () => `he_audio_resume_${playingMediaId}`

const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const bufferedTime = ref(0)
const isScrubbing = ref(false)
const volume = ref(Number(localStorage.getItem('he_audio_volume') ?? '1'))
const isMuted = ref(localStorage.getItem('he_audio_muted') === 'true')
const loopMode = ref<LoopMode>(
  (localStorage.getItem('he_audio_loop') as LoopMode) || 'list'
)

const playbackRates = [1.0, 1.25, 1.5, 2.0, 0.75]
const playbackRate = ref(1.0)

const lyrics = ref<LyricLine[]>([])
const lyricsLoading = ref(false)
const showLyrics = ref(false)
const lyricsContainerRef = ref<HTMLDivElement | null>(null)

const streamUrl = computed(() => authUrl(`${API_BASE_URL}/audio/${props.media.id}/track/${currentIndex.value}`))

const currentTrack = computed(() => {
  return tracks.value.find(t => t.index === currentIndex.value) || null
})

const formatTime = (seconds: number) => {
  if (!seconds || isNaN(seconds) || seconds < 0) return '00:00'
  const s = Math.floor(seconds)
  const m = Math.floor(s / 60)
  const r = s % 60
  if (m >= 60) {
    const h = Math.floor(m / 60)
    const remM = m % 60
    return `${h}:${remM.toString().padStart(2, '0')}:${r.toString().padStart(2, '0')}`
  }
  return `${m.toString().padStart(2, '0')}:${r.toString().padStart(2, '0')}`
}

const fetchTracks = async () => {
  const activeRequest = ++requestId
  saveResume(true)
  playingMediaId = props.media.id
  audioRef.value?.pause()
  isPlaying.value = false
  currentTime.value = 0; duration.value = 0; bufferedTime.value = 0
  playbackError.value = ''
  loading.value = true
  error.value = ''
  try {
    const response = await axios.get(`${API_BASE_URL}/audio/${props.media.id}/tracks`)
    if (activeRequest !== requestId) return
    tracks.value = response.data?.tracks || []
    let saved: { index?: number; time?: number } = {}
    try { saved = JSON.parse(localStorage.getItem(resumeKey()) || '{}') } catch { /* optional */ }
    const track = tracks.value.find(track => track.index === saved.index)
    currentIndex.value = track?.index ?? tracks.value[0]?.index ?? 1
    resumeTime = track && Number.isFinite(saved.time) ? Math.max(0, saved.time || 0) : 0
    await nextTick()
    audioRef.value?.load()
    void fetchLyrics()
  } catch (err: any) {
    if (activeRequest !== requestId) return
    error.value = err.response?.data?.detail || '读取音轨失败'
    tracks.value = []
  } finally {
    if (activeRequest === requestId) loading.value = false
  }
}

const fetchLyrics = async () => {
  const activeRequest = ++lyricsRequestId
  lyricsLoading.value = false
  lyrics.value = []
  if (!currentTrack.value?.lyrics) return
  lyricsLoading.value = true
  try {
    const res = await axios.get(`${API_BASE_URL}/audio/${props.media.id}/track/${currentIndex.value}/lyrics`)
    if (activeRequest === lyricsRequestId) lyrics.value = res.data?.lines || []
  } catch {
    if (activeRequest === lyricsRequestId) lyrics.value = []
  } finally {
    if (activeRequest === lyricsRequestId) lyricsLoading.value = false
  }
}

const activeLyricIndex = computed(() => {
  if (!lyrics.value.length) return -1
  const t = currentTime.value
  let idx = -1
  for (let i = 0; i < lyrics.value.length; i++) {
    if (lyrics.value[i].t <= t) {
      idx = i
    } else {
      break
    }
  }
  return idx
})

watch(activeLyricIndex, (idx) => {
  if (!showLyrics.value || idx < 0 || !lyricsContainerRef.value) return
  const lineEl = document.getElementById(`lyric-line-${idx}`)
  if (lineEl) {
    lineEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
})

const seekToLyric = (time: number) => {
  const audio = audioRef.value
  if (!audio) return
  audio.currentTime = Math.max(0, time)
  currentTime.value = audio.currentTime
}

const playTrack = (index: number) => {
  saveResume(true)
  resumeTime = 0
  playbackError.value = ''
  currentIndex.value = index
  currentTime.value = 0
  duration.value = 0
  bufferedTime.value = 0
  void nextTick(() => {
    const audio = audioRef.value
    if (!audio) return
    audio.load()
    audio.playbackRate = playbackRate.value
    audio.play().catch(() => { playbackError.value = '播放未开始，请点击播放按钮重试。' })
  })
}

const togglePlay = () => {
  const audio = audioRef.value
  if (!audio) return
  playbackError.value = ''
  if (audio.paused) {
    audio.play().catch(() => { playbackError.value = '播放未开始，请点击播放按钮重试。' })
  } else {
    audio.pause()
  }
}

const seekRelative = (seconds: number) => {
  const audio = audioRef.value
  if (!audio) return
  const target = Math.max(0, Math.min(duration.value || 0, audio.currentTime + seconds))
  audio.currentTime = target
  currentTime.value = target
}

const prevTrack = () => {
  const audio = audioRef.value
  if (audio && audio.currentTime > 3) {
    audio.currentTime = 0
    currentTime.value = 0
    return
  }
  const idx = tracks.value.findIndex(t => t.index === currentIndex.value)
  if (idx > 0) {
    playTrack(tracks.value[idx - 1].index)
  } else if (loopMode.value === 'list' && tracks.value.length > 0) {
    playTrack(tracks.value[tracks.value.length - 1].index)
  }
}

const nextTrack = () => {
  if (tracks.value.length === 0) return
  if (loopMode.value === 'shuffle') {
    const remaining = tracks.value.filter(t => t.index !== currentIndex.value)
    if (remaining.length > 0) {
      const pick = remaining[Math.floor(Math.random() * remaining.length)]
      playTrack(pick.index)
      return
    }
  }
  const idx = tracks.value.findIndex(t => t.index === currentIndex.value)
  if (idx < tracks.value.length - 1) {
    playTrack(tracks.value[idx + 1].index)
  } else if (loopMode.value === 'list' && tracks.value.length > 0) {
    playTrack(tracks.value[0].index)
  }
}

const toggleLoopMode = () => {
  if (loopMode.value === 'list') loopMode.value = 'single'
  else if (loopMode.value === 'single') loopMode.value = 'shuffle'
  else if (loopMode.value === 'shuffle') loopMode.value = 'off'
  else loopMode.value = 'list'
  localStorage.setItem('he_audio_loop', loopMode.value)
}

const cyclePlaybackRate = () => {
  const curIdx = playbackRates.indexOf(playbackRate.value)
  const nextRate = playbackRates[(curIdx + 1) % playbackRates.length]
  playbackRate.value = nextRate
  const audio = audioRef.value
  if (audio) {
    audio.playbackRate = nextRate
  }
}

const setVolume = (val: number) => {
  volume.value = Math.max(0, Math.min(1, val))
  localStorage.setItem('he_audio_volume', String(volume.value))
  if (isMuted.value && volume.value > 0) {
    isMuted.value = false
    localStorage.setItem('he_audio_muted', 'false')
  }
  const audio = audioRef.value
  if (audio) {
    audio.volume = volume.value
    audio.muted = isMuted.value
  }
}

const toggleMute = () => {
  isMuted.value = !isMuted.value
  localStorage.setItem('he_audio_muted', String(isMuted.value))
  const audio = audioRef.value
  if (audio) {
    audio.muted = isMuted.value
  }
}

const onTimeUpdate = () => {
  const audio = audioRef.value
  if (!audio || isScrubbing.value) return
  saveResume()
  syncPositionState()
  currentTime.value = audio.currentTime
  if (audio.buffered.length > 0) {
    bufferedTime.value = audio.buffered.end(audio.buffered.length - 1)
  }
}

const onLoadedMetadata = () => {
  const audio = audioRef.value
  if (!audio) return
  duration.value = Number.isFinite(audio.duration) ? audio.duration : 0
  if (resumeTime > 0 && resumeTime < duration.value - 2) {
    audio.currentTime = resumeTime
    currentTime.value = resumeTime
  }
  resumeTime = 0
  audio.volume = volume.value
  audio.muted = isMuted.value
  audio.playbackRate = playbackRate.value
}

const onScrubInput = (event: Event) => {
  const target = Number((event.target as HTMLInputElement).value)
  currentTime.value = target
}

const onScrubChange = (event: Event) => {
  const target = Number((event.target as HTMLInputElement).value)
  const audio = audioRef.value
  if (audio) {
    audio.currentTime = target
  }
  currentTime.value = target
  isScrubbing.value = false
}

const onEnded = () => {
  if (loopMode.value === 'single') {
    const audio = audioRef.value
    if (audio) {
      audio.currentTime = 0
      audio.play().catch(() => { playbackError.value = '播放未开始，请点击播放按钮重试。' })
    }
    return
  }
  nextTrack()
}

const saveResume = (force = false) => {
  const audio = audioRef.value
  if (!audio || !tracks.value.length || (!force && Date.now() - lastSavedAt < 5000)) return
  lastSavedAt = Date.now()
  try { localStorage.setItem(resumeKey(), JSON.stringify({ index: currentIndex.value, time: audio.currentTime || 0 })) } catch { /* optional */ }
}
const syncPositionState = () => {
  if (!('mediaSession' in navigator) || !navigator.mediaSession.setPositionState) return
  const audio = audioRef.value
  if (!audio || !Number.isFinite(audio.duration) || audio.duration <= 0) return
  try { navigator.mediaSession.setPositionState({ duration: audio.duration, playbackRate: audio.playbackRate, position: Math.min(audio.duration, Math.max(0, audio.currentTime)) }) } catch { /* unavailable on some WebKit versions */ }
}
const syncSystemPlayback = (playing: boolean) => {
  isPlaying.value = playing
  if (!playing) saveResume(true)
  if ('mediaSession' in navigator) navigator.mediaSession.playbackState = playing ? 'playing' : 'paused'
}
watch([isPlaying, currentTime, duration, currentTrack], () => {
  if (audioPlaybackStore.state.media?.id !== props.media.id) return
  Object.assign(audioPlaybackStore.state, { playing: isPlaying.value, trackTitle: currentTrack.value?.title || '', currentTime: currentTime.value, duration: duration.value })
})
watch([() => props.media.title, () => props.coverUrl, currentTrack], () => {
  if (!('mediaSession' in navigator) || typeof MediaMetadata === 'undefined') return
  navigator.mediaSession.metadata = new MediaMetadata({ title: currentTrack.value?.title || props.media.title, artist: props.media.title, album: 'HE Manager', artwork: props.coverUrl ? [{ src: new URL(props.coverUrl, window.location.href).href }] : [] })
}, { immediate: true })
const saveBeforePageHide = () => saveResume(true)
onMounted(() => {
  window.addEventListener('pagehide', saveBeforePageHide)
  audioPlaybackStore.bind({ togglePlay, nextTrack, prevTrack })
  if (!('mediaSession' in navigator)) return
  const handlers: Partial<Record<MediaSessionAction, MediaSessionActionHandler>> = {
    play: () => { audioRef.value?.play().catch(() => { playbackError.value = '请打开播放器后点击播放。' }) },
    pause: () => audioRef.value?.pause(),
    previoustrack: prevTrack, nexttrack: nextTrack,
    seekbackward: details => seekRelative(-(details.seekOffset || 10)),
    seekforward: details => seekRelative(details.seekOffset || 10),
    seekto: details => {
      if (audioRef.value && details.seekTime !== undefined) { audioRef.value.currentTime = details.seekTime; currentTime.value = details.seekTime }
    },
    stop: () => audioPlaybackStore.stop(),
  }
  for (const [action, handler] of Object.entries(handlers)) {
    try { navigator.mediaSession.setActionHandler(action as MediaSessionAction, handler!) } catch { /* unsupported action */ }
  }
})

watch(currentIndex, () => {
  fetchLyrics()
})

watch(() => props.media.id, fetchTracks, { immediate: true })

onBeforeUnmount(() => {
  window.removeEventListener('pagehide', saveBeforePageHide)
  saveResume(true)
  requestId++; lyricsRequestId++
  audioPlaybackStore.bind(null)
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = null
    navigator.mediaSession.playbackState = 'none'
    for (const action of ['play', 'pause', 'previoustrack', 'nexttrack', 'seekbackward', 'seekforward', 'seekto', 'stop']) {
      try { navigator.mediaSession.setActionHandler(action as MediaSessionAction, null) } catch { /* unsupported */ }
    }
  }
  const audio = audioRef.value
  if (audio) {
    audio.pause()
    audio.src = ''
  }
})
</script>

<template>
  <div class="he-audio-player relative flex min-h-0 flex-1 flex-col overflow-hidden bg-black text-white">
    <!-- Hidden native audio element -->
    <audio
      ref="audioRef"
      :src="streamUrl"
      preload="metadata"
      class="hidden"
      @play="syncSystemPlayback(true)"
      @pause="syncSystemPlayback(false)"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMetadata"
      @ended="onEnded"
      @error="playbackError = tracks.length ? '音轨加载失败，请切换音轨或重试。' : ''"
    />

    <!-- Track tools sit below the viewer header in the normal layout flow. -->
    <div class="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-white/10 px-4 py-2 sm:px-6">
      <span class="min-w-0 truncate text-meta text-white/60 tabular-nums">
        {{ tracks.length ? `音轨 ${currentIndex} / ${tracks.length}` : loading ? '正在读取音轨…' : '播放列表' }}
      </span>
      <button
        v-if="currentTrack?.lyrics"
        type="button"
        class="he-audio-chip gap-1.5 px-3"
        :class="showLyrics ? 'bg-white/15 text-white' : 'text-white/75 hover:bg-white/10 hover:text-white'"
        :aria-pressed="showLyrics"
        title="切换歌词/唱片视图"
        @click="showLyrics = !showLyrics"
      >
        <FileText :size="15" aria-hidden="true" />
        <span>歌词</span>
      </button>
    </div>

    <p v-if="playbackError" role="alert" class="shrink-0 border-b border-danger/25 bg-danger/10 px-4 py-2 text-meta text-danger sm:px-6">{{ playbackError }}</p>

    <div class="he-audio-body flex min-h-0 flex-1 flex-col lg:flex-row">
      <!-- Stage: artwork or synchronized lyrics, track info and transport -->
      <div class="he-audio-stage flex shrink-0 flex-col items-center justify-center px-6 py-8 lg:w-[46%] lg:max-w-[640px] lg:px-10">
        <div
          v-if="showLyrics"
          ref="lyricsContainerRef"
          class="custom-scrollbar aspect-square w-full max-w-60 select-none overflow-y-auto rounded-2xl bg-white/5 px-5 py-10 text-center ring-1 ring-inset ring-white/10 sm:max-w-72 lg:max-w-sm"
        >
          <div v-if="lyricsLoading" class="py-12 text-meta text-white/55">正在加载歌词…</div>
          <div v-else-if="lyrics.length === 0" class="py-12 text-meta text-white/55">暂无可用同步歌词</div>
          <div v-else class="space-y-2.5">
            <p
              v-for="(line, i) in lyrics"
              :key="i"
              :id="`lyric-line-${i}`"
              class="cursor-pointer select-none transition-colors duration-200"
              :class="i === activeLyricIndex
                ? 'text-body font-semibold text-white'
                : 'text-meta text-white/45 hover:text-white/80'"
              @click="seekToLyric(line.t)"
            >
              {{ line.text }}
            </p>
          </div>
        </div>

        <div v-else class="relative aspect-square w-full max-w-60 select-none overflow-hidden rounded-2xl bg-white/5 sm:max-w-72 lg:max-w-sm">
          <img v-if="coverUrl" :src="coverUrl" class="pointer-events-none h-full w-full object-cover" :alt="media.title" />
          <div v-else class="grid h-full w-full place-items-center text-white/40">
            <Music :size="40" aria-hidden="true" />
          </div>
          <div class="pointer-events-none absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/10"></div>
        </div>

        <div class="mt-6 w-full max-w-sm text-center">
          <h4 class="truncate text-heading font-semibold text-white" :title="currentTrack?.title || media.title">
            {{ currentTrack?.title || media.title }}
          </h4>
          <div class="mt-1 flex min-w-0 items-center justify-center gap-2">
            <span v-if="currentTrack?.lyrics" class="inline-flex h-5 shrink-0 items-center rounded-md bg-white/10 px-1.5 text-caption font-medium text-white/80">LRC</span>
            <span class="truncate text-meta text-white/60">{{ media.title }}</span>
          </div>
        </div>

        <div class="mt-5 w-full max-w-sm">
          <div class="relative flex h-5 cursor-pointer items-center">
            <div class="relative h-1 w-full overflow-hidden rounded-sm bg-white/15">
              <div
                class="absolute inset-y-0 left-0 bg-white/25"
                :style="{ width: `${duration ? Math.min(100, (bufferedTime / duration) * 100) : 0}%` }"
              ></div>
              <div
                class="absolute inset-y-0 left-0 bg-accent"
                :style="{ width: `${duration ? Math.min(100, (currentTime / duration) * 100) : 0}%` }"
              ></div>
            </div>
            <input
              type="range"
              :min="0"
              :max="duration || 1"
              :value="currentTime"
              step="0.1"
              aria-label="音频播放进度"
              class="absolute inset-0 h-full w-full cursor-pointer opacity-0"
              @pointerdown="isScrubbing = true" @pointercancel="isScrubbing = false"
              @input="onScrubInput"
              @change="onScrubChange"
            />
          </div>
          <div class="mt-0.5 flex justify-between text-caption text-white/55 tabular-nums">
            <span>{{ formatTime(currentTime) }}</span>
            <span>{{ formatTime(duration) }}</span>
          </div>

          <div class="he-audio-controls mt-3 flex items-center justify-center gap-2 sm:gap-3">
            <button type="button" class="he-audio-btn" aria-label="上一首" title="上一首" @click="prevTrack">
              <SkipBack :size="20" aria-hidden="true" />
            </button>
            <button type="button" class="he-audio-btn" aria-label="快退 5 秒" title="快退 5 秒" @click="seekRelative(-5)">
              <RotateCcw :size="19" aria-hidden="true" />
            </button>
            <button
              type="button"
              class="mx-1 grid size-14 shrink-0 place-items-center rounded-full bg-accent text-on-accent transition-colors duration-150 hover:bg-accent/90 focus-ring"
              :aria-label="isPlaying ? '暂停' : '播放'" :title="isPlaying ? '暂停' : '播放'"
              @click="togglePlay"
            >
              <Pause v-if="isPlaying" :size="22" class="fill-current" aria-hidden="true" />
              <Play v-else :size="22" class="ml-0.5 fill-current" aria-hidden="true" />
            </button>
            <button type="button" class="he-audio-btn" aria-label="快进 5 秒" title="快进 5 秒" @click="seekRelative(5)">
              <RotateCw :size="19" aria-hidden="true" />
            </button>
            <button type="button" class="he-audio-btn" aria-label="下一首" title="下一首" @click="nextTrack">
              <SkipForward :size="20" aria-hidden="true" />
            </button>
          </div>

          <div class="mt-3 flex items-center justify-between gap-2">
            <button
              type="button"
              class="he-audio-chip w-9 pointer-coarse:w-11"
              :class="loopMode !== 'off' ? 'bg-accent/20 text-accent-glow' : 'text-white/65 hover:bg-white/10 hover:text-white'"
              :aria-label="loopMode === 'list' ? '列表循环' : loopMode === 'single' ? '单曲循环' : loopMode === 'shuffle' ? '随机播放' : '顺序播放 (单次)'"
              :title="loopMode === 'list' ? '列表循环' : loopMode === 'single' ? '单曲循环' : loopMode === 'shuffle' ? '随机播放' : '顺序播放 (单次)'"
              @click="toggleLoopMode"
            >
              <Repeat1 v-if="loopMode === 'single'" :size="17" aria-hidden="true" />
              <Shuffle v-else-if="loopMode === 'shuffle'" :size="17" aria-hidden="true" />
              <Repeat v-else :size="17" aria-hidden="true" />
            </button>

            <div class="flex items-center gap-2">
              <button
                type="button"
                class="he-audio-chip min-w-11 px-2 tabular-nums"
                :class="playbackRate !== 1.0 ? 'bg-accent/20 text-accent-glow' : 'text-white/70 hover:bg-white/10 hover:text-white'"
                data-audio-rate title="点击切换播放倍速"
                :aria-label="`播放倍速 ${playbackRate}×`"
                @click="cyclePlaybackRate"
              >
                {{ playbackRate }}×
              </button>

              <div class="he-audio-volume flex items-center gap-1">
                <button
                  type="button"
                  class="he-audio-chip w-9 text-white/70 hover:bg-white/10 hover:text-white"
                  :aria-label="isMuted ? '取消静音' : '静音'"
                  :title="isMuted ? '取消静音' : '静音'"
                  @click="toggleMute"
                >
                  <VolumeX v-if="isMuted || volume === 0" :size="17" aria-hidden="true" />
                  <Volume1 v-else-if="volume < 0.5" :size="17" aria-hidden="true" />
                  <Volume2 v-else :size="17" aria-hidden="true" />
                </button>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.02"
                  :value="isMuted ? 0 : volume"
                  class="he-audio-range w-20 cursor-pointer"
                  :style="{ '--fill': `${Math.round((isMuted ? 0 : volume) * 100)}%` }"
                  aria-label="音量"
                  :title="`音量: ${Math.round((isMuted ? 0 : volume) * 100)}%`"
                  @input="(e) => setVolume(Number((e.target as HTMLInputElement).value))"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tracklist -->
      <div class="he-audio-tracks custom-scrollbar min-h-0 flex-1 overflow-y-auto border-t border-white/10 px-3 py-4 sm:px-6 lg:border-l lg:border-t-0 lg:py-6">
        <div v-if="loading" class="py-6 text-center text-meta text-white/60">正在加载音轨…</div>
        <div v-else-if="error" class="py-6 text-center text-meta text-danger">{{ error }}</div>
        <div v-else-if="tracks.length === 0" class="py-6 text-center text-meta text-white/55">没有可播放的音轨</div>
        <div v-else class="mx-auto max-w-3xl">
          <div class="mb-2 flex items-baseline justify-between px-3">
            <span class="text-body font-medium text-white">播放列表 <span class="ml-1 text-meta font-normal text-white/55 tabular-nums">{{ tracks.length }} 首</span></span>
            <span class="text-caption text-white/45 pointer-coarse:hidden">点击曲目切换</span>
          </div>
          <div class="space-y-0.5">
            <button
              v-for="track in tracks"
              :key="track.index"
              type="button"
              :class="track.index === currentIndex
                ? 'bg-white/10 text-white'
                : 'text-white/80 hover:bg-white/5 hover:text-white'"
              class="flex min-h-12 w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors duration-150 focus-ring-inset"
              :aria-current="track.index === currentIndex ? 'true' : undefined"
              @click="playTrack(track.index)"
            >
              <span class="grid w-6 shrink-0 place-items-center text-caption tabular-nums" :class="track.index === currentIndex ? 'text-accent-glow' : 'text-white/45'">
                <Volume2 v-if="track.index === currentIndex && isPlaying" :size="15" aria-label="正在播放" />
                <template v-else>{{ track.index.toString().padStart(2, '0') }}</template>
              </span>
              <span class="min-w-0 flex-1 truncate text-body" :class="track.index === currentIndex ? 'font-medium' : ''">
                {{ track.title }}
              </span>
              <span v-if="track.lyrics" class="inline-flex h-5 shrink-0 items-center rounded-md bg-white/10 px-1.5 text-caption font-medium text-white/75">LRC</span>
              <span v-if="track.duration" class="shrink-0 text-meta text-white/55 tabular-nums">
                {{ formatTime(track.duration) }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.he-audio-btn {
  display: grid;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 9999px;
  color: rgb(255 255 255 / 0.8);
  transition: background-color 120ms var(--ease-out), color 120ms var(--ease-out);
}
.he-audio-btn:hover { background: rgb(255 255 255 / 0.1); color: #fff; }
.he-audio-chip {
  display: inline-flex;
  height: 36px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  font-size: var(--text-meta);
  font-weight: 500;
  transition: background-color 120ms var(--ease-out), color 120ms var(--ease-out);
}
@media (pointer: coarse) {
  .he-audio-chip { height: 44px; min-width: 44px; }
}
.he-audio-range { appearance: none; -webkit-appearance: none; height: 20px; background: transparent; }
.he-audio-range::-webkit-slider-runnable-track { height: 4px; border-radius: 4px; background: linear-gradient(to right, rgb(255 255 255 / 0.85) var(--fill, 0%), rgb(255 255 255 / 0.2) var(--fill, 0%)); }
.he-audio-range::-moz-range-track { height: 4px; border-radius: 4px; background: linear-gradient(to right, rgb(255 255 255 / 0.85) var(--fill, 0%), rgb(255 255 255 / 0.2) var(--fill, 0%)); }
.he-audio-range::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; margin-top: -4px; border-radius: 9999px; background: #fff; }
.he-audio-range::-moz-range-thumb { width: 12px; height: 12px; border: 0; border-radius: 9999px; background: #fff; }
@media (max-width: 899px) {
  .he-audio-player { overflow-y: auto; padding-bottom: env(safe-area-inset-bottom); }
  .he-audio-body { flex: none; }
  .he-audio-tracks { flex: none; overflow: visible; }
  .he-audio-stage { padding: 24px 16px 20px; }
  .he-audio-stage h4 { white-space: normal; }
  .he-audio-volume { display: none; }
  .he-audio-stage input[type="range"] { min-height: 32px; }
}
</style>
