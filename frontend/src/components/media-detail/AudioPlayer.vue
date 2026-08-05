<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import axios from 'axios'
import { API_BASE_URL, authUrl } from '../../config'
import type { Media } from '../../types'

interface AudioTrack {
  index: number
  title: string
  rel: string
  duration: number | null
  lyrics: string | null
}

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

const streamUrl = computed(() => authUrl(`${API_BASE_URL}/audio/${props.media.id}/track/${currentIndex.value}`))

const fetchTracks = async () => {
  const activeRequest = ++requestId
  loading.value = true
  error.value = ''
  try {
    const response = await axios.get(`${API_BASE_URL}/audio/${props.media.id}/tracks`)
    if (activeRequest !== requestId) return
    tracks.value = response.data?.tracks || []
    currentIndex.value = tracks.value[0]?.index ?? 1
  } catch (err: any) {
    if (activeRequest !== requestId) return
    error.value = err.response?.data?.detail || '读取音轨失败'
    tracks.value = []
  } finally {
    if (activeRequest === requestId) loading.value = false
  }
}

const playTrack = (index: number) => {
  currentIndex.value = index
  void nextTick(() => {
    const audio = audioRef.value
    if (!audio) return
    audio.load()
    audio.play().catch(() => { /* user gesture may still be required */ })
  })
}

const onEnded = () => {
  const index = tracks.value.findIndex(track => track.index === currentIndex.value)
  const next = tracks.value[index + 1]
  if (next) playTrack(next.index)
}

watch(() => props.media.id, fetchTracks, { immediate: true })
</script>

<template>
  <div class="relative flex-1 min-h-0 bg-black overflow-hidden flex flex-col">
    <div class="flex items-center gap-5 px-6 py-5 border-b border-white/10 bg-gradient-to-b from-black/40 to-transparent">
      <div class="w-24 h-24 rounded-2xl bg-white/5 border border-white/10 overflow-hidden shrink-0 flex items-center justify-center">
        <img v-if="coverUrl" :src="coverUrl" class="w-full h-full object-cover" :alt="media.title" />
        <span v-else class="text-white/30 text-xs">无封面</span>
      </div>
      <div class="min-w-0 flex-1">
        <h3 class="text-xl font-black text-white truncate">{{ media.title }}</h3>
        <p class="text-xs text-white/45 mt-1 truncate">{{ media.relative_path }}</p>
        <p class="text-[11px] text-white/35 mt-1">Web 端为基础播放；歌词跟随、循环、休眠定时器请用 Android App</p>
      </div>
    </div>

    <div class="px-6 py-4 border-b border-white/10 bg-black/30">
      <div v-if="loading" class="text-sm text-white/55">正在加载音轨…</div>
      <div v-else-if="error" class="text-sm text-red-300">{{ error }}</div>
      <div v-else-if="tracks.length === 0" class="text-sm text-white/45">没有可播放的音轨</div>
      <div v-else class="space-y-3">
        <p class="text-[11px] font-bold text-white/55 uppercase tracking-widest">
          正在播放 · 第 {{ currentIndex }} / {{ tracks.length }} 轨
        </p>
        <audio ref="audioRef" :src="streamUrl" controls preload="metadata" class="w-full" @ended="onEnded" />
      </div>
    </div>

    <div class="flex-1 overflow-y-auto px-2 py-2">
      <button
        v-for="track in tracks"
        :key="track.index"
        type="button"
        @click="playTrack(track.index)"
        :class="track.index === currentIndex
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
</template>
