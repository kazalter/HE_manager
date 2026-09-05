<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
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
  loading.value = true
  error.value = ''
  try {
    const response = await axios.get(`${API_BASE_URL}/audio/${props.media.id}/tracks`)
    if (activeRequest !== requestId) return
    tracks.value = response.data?.tracks || []
    currentIndex.value = tracks.value[0]?.index ?? 1
    fetchLyrics()
  } catch (err: any) {
    if (activeRequest !== requestId) return
    error.value = err.response?.data?.detail || '读取音轨失败'
    tracks.value = []
  } finally {
    if (activeRequest === requestId) loading.value = false
  }
}

const fetchLyrics = async () => {
  lyrics.value = []
  if (!currentTrack.value?.lyrics) return
  lyricsLoading.value = true
  try {
    const res = await axios.get(`${API_BASE_URL}/audio/${props.media.id}/track/${currentIndex.value}/lyrics`)
    lyrics.value = res.data?.lines || []
  } catch {
    lyrics.value = []
  } finally {
    lyricsLoading.value = false
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
  currentIndex.value = index
  currentTime.value = 0
  duration.value = 0
  bufferedTime.value = 0
  void nextTick(() => {
    const audio = audioRef.value
    if (!audio) return
    audio.load()
    audio.playbackRate = playbackRate.value
    audio.play().catch(() => {})
  })
}

const togglePlay = () => {
  const audio = audioRef.value
  if (!audio) return
  if (audio.paused) {
    audio.play().catch(() => {})
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
  currentTime.value = audio.currentTime
  if (audio.buffered.length > 0) {
    bufferedTime.value = audio.buffered.end(audio.buffered.length - 1)
  }
}

const onLoadedMetadata = () => {
  const audio = audioRef.value
  if (!audio) return
  duration.value = audio.duration || 0
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
      audio.play().catch(() => {})
    }
    return
  }
  nextTrack()
}

watch(currentIndex, () => {
  fetchLyrics()
})

watch(() => props.media.id, fetchTracks, { immediate: true })

onBeforeUnmount(() => {
  const audio = audioRef.value
  if (audio) {
    audio.pause()
    audio.src = ''
  }
})
</script>

<template>
  <div class="relative flex-1 min-h-0 bg-gradient-to-b from-[#0e0e12] to-black overflow-hidden flex flex-col">
    <!-- Hidden native audio element -->
    <audio
      ref="audioRef"
      :src="streamUrl"
      preload="metadata"
      class="hidden"
      @play="isPlaying = true"
      @pause="isPlaying = false"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMetadata"
      @ended="onEnded"
    />

    <!-- Header info banner -->
    <div class="flex items-center gap-4 px-6 py-4 border-b border-white/10 bg-black/40 backdrop-blur-md">
      <div class="min-w-0 flex-1">
        <h3 class="text-lg font-black text-white truncate">{{ media.title }}</h3>
        <p class="text-xs text-white/45 truncate mt-0.5">{{ media.relative_path }}</p>
      </div>
      <div v-if="tracks.length > 0" class="flex items-center gap-3 shrink-0">
        <!-- Lyrics toggle button -->
        <button
          v-if="currentTrack?.lyrics"
          type="button"
          @click="showLyrics = !showLyrics"
          class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer"
          :class="showLyrics ? 'bg-accent text-white shadow-md' : 'bg-white/8 text-white/70 hover:bg-white/15 hover:text-white'"
          title="切换歌词/唱片视图"
        >
          <FileText :size="13" />
          <span>歌词</span>
        </button>
        <span class="text-xs font-mono text-white/50">音轨 {{ currentIndex }} / {{ tracks.length }}</span>
      </div>
    </div>

    <!-- Center Stage: Vinyl Disc or Synchronized Lyrics View -->
    <div class="flex flex-col items-center justify-center py-4 px-6 relative shrink-0 min-h-[220px]">
      <!-- Glow backlight -->
      <div
        class="absolute w-64 h-64 rounded-full bg-accent/20 blur-3xl pointer-events-none transition-opacity duration-700"
        :class="isPlaying ? 'opacity-80 scale-105' : 'opacity-20 scale-95'"
      ></div>

      <!-- Realtime Scrolling Lyrics View -->
      <div
        v-if="showLyrics"
        ref="lyricsContainerRef"
        class="w-full max-w-md h-52 overflow-y-auto custom-scrollbar text-center py-8 px-4 rounded-2xl bg-black/40 border border-white/8 backdrop-blur-md select-none"
      >
        <div v-if="lyricsLoading" class="text-sm text-white/40 py-12">正在加载歌词...</div>
        <div v-else-if="lyrics.length === 0" class="text-sm text-white/40 py-12">暂无可用同步歌词</div>
        <div v-else class="space-y-2">
          <p
            v-for="(line, i) in lyrics"
            :key="i"
            :id="`lyric-line-${i}`"
            @click="seekToLyric(line.t)"
            class="py-1 transition-all duration-300 cursor-pointer select-none"
            :class="i === activeLyricIndex
              ? 'text-accent font-black text-base scale-105 drop-shadow-[0_0_12px_rgba(129,140,248,0.7)]'
              : 'text-white/40 hover:text-white/80 text-xs'"
          >
            {{ line.text }}
          </p>
        </div>
      </div>

      <!-- Vinyl Disc View -->
      <div
        v-else
        class="relative w-40 h-40 sm:w-48 sm:h-48 rounded-full bg-gradient-to-tr from-neutral-950 via-neutral-900 to-neutral-800 border-[5px] border-neutral-700/40 shadow-2xl flex items-center justify-center select-none"
        :class="isPlaying ? 'animate-[spin_24s_linear_infinite]' : ''"
      >
        <!-- Vinyl Grooves -->
        <div class="absolute inset-2 rounded-full border border-white/5 pointer-events-none"></div>
        <div class="absolute inset-5 rounded-full border border-white/5 pointer-events-none"></div>
        <div class="absolute inset-8 rounded-full border border-white/5 pointer-events-none"></div>

        <!-- Disc Center Label / Artwork -->
        <div class="w-20 h-20 sm:w-24 sm:h-24 rounded-full overflow-hidden border-2 border-white/20 shadow-inner bg-neutral-900 flex items-center justify-center relative">
          <img v-if="coverUrl" :src="coverUrl" class="w-full h-full object-cover pointer-events-none" :alt="media.title" />
          <Music v-else :size="28" class="text-white/40" />
          <!-- Spindle center hole -->
          <div class="absolute w-3.5 h-3.5 rounded-full bg-neutral-950 border border-white/20 shadow-inner"></div>
        </div>
      </div>

      <!-- Current Track Info Display -->
      <div class="mt-3 text-center max-w-md w-full px-4">
        <h4 class="text-base font-bold text-white truncate">
          {{ currentTrack?.title || media.title }}
        </h4>
        <div class="flex items-center justify-center gap-2 mt-0.5">
          <span v-if="currentTrack?.lyrics" class="text-[10px] font-black text-accent bg-accent/15 px-1.5 py-0.2 rounded uppercase tracking-wider">
            LRC
          </span>
          <span class="text-xs font-mono text-white/45">
            {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
          </span>
        </div>
      </div>

      <!-- Player Controls Deck -->
      <div class="w-full max-w-md mt-3 px-2 space-y-2.5">
        <!-- Progress Bar (Scrubber) -->
        <div class="space-y-1">
          <div class="relative flex items-center h-4 group/progress cursor-pointer">
            <!-- Background track -->
            <div class="w-full h-1.5 rounded-full bg-white/10 overflow-hidden relative">
              <!-- Buffer bar -->
              <div
                class="absolute inset-y-0 left-0 bg-white/20 rounded-full transition-all duration-200"
                :style="{ width: `${duration ? Math.min(100, (bufferedTime / duration) * 100) : 0}%` }"
              ></div>
              <!-- Played bar -->
              <div
                class="absolute inset-y-0 left-0 bg-accent rounded-full"
                :style="{ width: `${duration ? Math.min(100, (currentTime / duration) * 100) : 0}%` }"
              ></div>
            </div>
            <!-- Interactive input range slider overlay -->
            <input
              type="range"
              :min="0"
              :max="duration || 1"
              :value="currentTime"
              step="0.1"
              @mousedown="isScrubbing = true"
              @input="onScrubInput"
              @change="onScrubChange"
              class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
          </div>
          <div class="flex justify-between text-[11px] font-mono text-white/40">
            <span>{{ formatTime(currentTime) }}</span>
            <span>{{ formatTime(duration) }}</span>
          </div>
        </div>

        <!-- Buttons Row -->
        <div class="flex items-center justify-between gap-1.5">
          <!-- Loop / Shuffle Mode Button -->
          <button
            type="button"
            @click="toggleLoopMode"
            class="w-8 h-8 rounded-xl flex items-center justify-center transition-all cursor-pointer"
            :class="loopMode !== 'off' ? 'text-accent bg-accent/15' : 'text-white/40 hover:text-white hover:bg-white/5'"
            :title="loopMode === 'list' ? '列表循环' : loopMode === 'single' ? '单曲循环' : loopMode === 'shuffle' ? '随机播放' : '顺序播放 (单次)'"
          >
            <Repeat1 v-if="loopMode === 'single'" :size="16" />
            <Shuffle v-else-if="loopMode === 'shuffle'" :size="16" />
            <Repeat v-else :size="16" />
          </button>

          <!-- Prev Track Button -->
          <button
            type="button"
            @click="prevTrack"
            class="w-8 h-8 rounded-xl flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
            title="上一首"
          >
            <SkipBack :size="17" />
          </button>

          <!-- Rewind 5s Button -->
          <button
            type="button"
            @click="seekRelative(-5)"
            class="w-8 h-8 rounded-xl flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
            title="快退 5 秒"
          >
            <RotateCcw :size="16" />
          </button>

          <!-- Big Play / Pause Button -->
          <button
            type="button"
            @click="togglePlay"
            class="w-11 h-11 rounded-full bg-accent text-white shadow-xl shadow-accent/30 hover:scale-105 active:scale-95 transition-all flex items-center justify-center cursor-pointer"
            :title="isPlaying ? '暂停' : '播放'"
          >
            <Pause v-if="isPlaying" :size="20" class="fill-current" />
            <Play v-else :size="20" class="fill-current ml-0.5" />
          </button>

          <!-- Fast Forward 5s Button -->
          <button
            type="button"
            @click="seekRelative(5)"
            class="w-8 h-8 rounded-xl flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
            title="快进 5 秒"
          >
            <RotateCw :size="16" />
          </button>

          <!-- Next Track Button -->
          <button
            type="button"
            @click="nextTrack"
            class="w-8 h-8 rounded-xl flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
            title="下一首"
          >
            <SkipForward :size="17" />
          </button>

          <!-- Playback Rate Button -->
          <button
            type="button"
            @click="cyclePlaybackRate"
            class="px-2 py-1 rounded-lg text-xs font-mono font-bold text-white/70 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
            :class="playbackRate !== 1.0 ? 'text-accent bg-accent/15' : ''"
            title="点击切换播放倍速"
          >
            {{ playbackRate }}x
          </button>

          <!-- Volume Controls -->
          <div class="flex items-center gap-1 pl-1">
            <button
              type="button"
              @click="toggleMute"
              class="w-7 h-7 rounded-lg flex items-center justify-center text-white/60 hover:text-white transition-colors cursor-pointer"
              :title="isMuted ? '取消静音' : '静音'"
            >
              <VolumeX v-if="isMuted || volume === 0" :size="15" />
              <Volume1 v-else-if="volume < 0.5" :size="15" />
              <Volume2 v-else :size="15" />
            </button>
            <input
              type="range"
              min="0"
              max="1"
              step="0.02"
              :value="isMuted ? 0 : volume"
              @input="(e) => setVolume(Number((e.target as HTMLInputElement).value))"
              class="w-14 sm:w-16 accent-accent h-1.5 rounded-full cursor-pointer bg-white/15 focus:outline-none"
              :title="`音量: ${Math.round((isMuted ? 0 : volume) * 100)}%`"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom Tracklist -->
    <div class="flex-1 overflow-y-auto px-4 py-2 custom-scrollbar border-t border-white/10 bg-black/30">
      <div v-if="loading" class="text-sm text-white/55 py-4 text-center">正在加载音轨…</div>
      <div v-else-if="error" class="text-sm text-red-300 py-4 text-center">{{ error }}</div>
      <div v-else-if="tracks.length === 0" class="text-sm text-white/45 py-4 text-center">没有可播放的音轨</div>
      <div v-else class="space-y-1 max-w-3xl mx-auto">
        <div class="text-[11px] font-bold text-white/40 uppercase tracking-wider px-3 py-1.5 flex items-center justify-between">
          <span>播放列表 ({{ tracks.length }})</span>
          <span class="text-[10px] text-white/30 font-normal">点击曲目切换</span>
        </div>
        <button
          v-for="track in tracks"
          :key="track.index"
          type="button"
          @click="playTrack(track.index)"
          :class="track.index === currentIndex
            ? 'bg-accent/20 border-accent/40 text-white shadow-sm'
            : 'border-white/5 text-white/70 hover:text-white hover:bg-white/[0.04]'"
          class="w-full text-left rounded-xl border px-3.5 py-2.5 transition-all flex items-center gap-3 cursor-pointer group"
        >
          <span
            class="text-xs font-mono w-6 shrink-0 text-center"
            :class="track.index === currentIndex ? 'text-accent font-bold' : 'text-white/40'"
          >
            {{ track.index === currentIndex && isPlaying ? '▶' : track.index.toString().padStart(2, '0') }}
          </span>
          <span class="flex-1 min-w-0 truncate text-sm font-medium" :class="track.index === currentIndex ? 'font-bold text-white' : ''">
            {{ track.title }}
          </span>
          <span v-if="track.duration" class="text-xs font-mono text-white/40 shrink-0">
            {{ formatTime(track.duration) }}
          </span>
          <span v-if="track.lyrics" class="text-[10px] font-black text-accent/80 bg-accent/10 px-1.5 py-0.5 rounded uppercase tracking-wider shrink-0">
            LRC
          </span>
        </button>
      </div>
    </div>
  </div>
</template>
