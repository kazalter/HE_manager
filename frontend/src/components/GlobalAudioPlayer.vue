<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ChevronDown, Headphones, Pause, Play, SkipForward, Star, X } from 'lucide-vue-next'
import axios from 'axios'
import { API_BASE_URL, thumbnailUrl } from '../config'
import { audioPlaybackStore as player } from '../stores/audioPlaybackStore'
import { useCompactViewport } from '../composables/useCompactViewport'
const AudioPlayer = defineAsyncComponent(() => import('./media-detail/AudioPlayer.vue'))
const compact = useCompactViewport()
const cover = computed(() => thumbnailUrl(player.state.media?.cover_path))
const panelRef = ref<HTMLElement | null>(null)
const minimizeRef = ref<HTMLButtonElement | null>(null)
const openRef = ref<HTMLButtonElement | null>(null)
const favoriteError = ref('')
watch(() => player.state.media?.id, async id => {
  if (!id) return
  try {
    const { data } = await axios.get(`${API_BASE_URL}/media/${id}`)
    if (player.state.media?.id !== id || data.media_type !== 'audio') return
    Object.assign(player.state.media, { last_opened_at: data.last_opened_at, view_status: data.view_status })
    window.dispatchEvent(new CustomEvent('he:media-updated', { detail: { ...player.state.media } }))
  } catch { /* Playback can continue when media metadata is unavailable. */ }
})
watch(() => player.state.expanded, async expanded => {
  await nextTick()
  if (expanded) minimizeRef.value?.focus()
  else openRef.value?.focus()
})
const toggleFavorite = async () => {
  const media = player.state.media
  if (!media) return
  favoriteError.value = ''
  try {
    const { data } = await axios.patch(`${API_BASE_URL}/media/${media.id}`, { favorite: !media.favorite })
    if (player.state.media?.id === media.id) player.state.media = data
    window.dispatchEvent(new CustomEvent('he:media-updated', { detail: data }))
  } catch { favoriteError.value = '收藏保存失败，请重试。' }
}
const onKeydown = (event: KeyboardEvent) => {
  if (!player.state.expanded) return
  if (event.key === 'Escape') { event.preventDefault(); player.minimize() }
  if (event.key !== 'Tab') return
  const elements = panelRef.value?.querySelectorAll<HTMLElement>('button:not([disabled]), input, a[href]')
  const focusable = Array.from(elements || []).filter(element => element.getClientRects().length)
  const first = focusable[0], last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
onBeforeUnmount(() => player.stop())
</script>
<template>
  <Teleport to="body">
    <div v-if="player.state.media" class="he-audio-host" :class="{ 'is-expanded': player.state.expanded, 'is-mobile': compact }">
      <section v-show="player.state.expanded" ref="panelRef" role="dialog" aria-modal="true" :aria-label="'音频播放器：' + player.state.media.title" class="he-audio-panel flex flex-col bg-background text-white" @keydown="onKeydown">
        <header class="he-audio-header flex items-center gap-3 p-3 border-b border-white/10 shrink-0">
          <button ref="minimizeRef" type="button" class="min-h-11 min-w-11 rounded-xl bg-white/10" aria-label="收起播放器，继续播放" @click="player.minimize"><ChevronDown :size="22" class="mx-auto" aria-hidden="true" /></button>
          <h2 class="min-w-0 flex-1 truncate font-bold">{{ player.state.media.title }}</h2>
          <button type="button" class="min-h-11 min-w-11 rounded-xl bg-white/10" :aria-pressed="player.state.media.favorite" :aria-label="player.state.media.favorite ? '取消收藏' : '收藏音频'" @click="toggleFavorite"><Star :size="20" class="mx-auto" :fill="player.state.media.favorite ? 'currentColor' : 'none'" aria-hidden="true" /></button>
          <button type="button" class="min-h-11 min-w-11 rounded-xl bg-red-500/20" aria-label="停止播放并关闭" @click="player.stop"><X :size="20" class="mx-auto" aria-hidden="true" /></button>
        </header>
        <p v-if="favoriteError" role="alert" class="px-4 py-2 text-sm text-red-300">{{ favoriteError }}</p>
        <AudioPlayer :media="player.state.media" :cover-url="cover" />
      </section>
      <div v-show="!player.state.expanded" class="he-mini-player flex items-center gap-2 text-white border border-white/15 rounded-2xl bg-sidebar shadow-xl px-2 py-1.5">
        <button ref="openRef" type="button" class="flex-1 min-w-0 flex items-center gap-3 min-h-12 text-left" aria-label="展开音频播放器" @click="player.state.expanded = true">
          <img v-if="cover" :src="cover" alt="" class="w-11 h-11 rounded-xl object-cover shrink-0" /><Headphones v-else :size="24" class="mx-2 shrink-0 text-accent" aria-hidden="true" />
          <span class="min-w-0"><span class="block text-sm font-bold truncate">{{ player.state.trackTitle || player.state.media.title }}</span><span class="block text-xs text-white/65 truncate">{{ player.state.media.title }}</span></span>
        </button>
        <button type="button" class="min-w-11 min-h-11 rounded-xl bg-accent/20" :aria-label="player.state.playing ? '暂停音频' : '播放音频'" @click="player.togglePlay"><Pause v-if="player.state.playing" :size="20" class="mx-auto" aria-hidden="true" /><Play v-else :size="20" class="mx-auto" aria-hidden="true" /></button>
        <button type="button" class="min-w-11 min-h-11 rounded-xl" aria-label="下一首音频" @click="player.nextTrack"><SkipForward :size="20" class="mx-auto" aria-hidden="true" /></button>
        <button type="button" class="min-w-11 min-h-11 rounded-xl" aria-label="停止音频" @click="player.stop"><X :size="18" class="mx-auto" aria-hidden="true" /></button>
        <div class="he-mini-progress" aria-hidden="true" :style="{ width: (player.state.duration ? Math.min(100, player.state.currentTime / player.state.duration * 100) : 0) + '%' }"></div>
      </div>
    </div>
  </Teleport>
</template>
<style>
.he-audio-host { position: fixed; z-index: 65; bottom: 20px; left: 50%; transform: translateX(-50%); width: min(600px, calc(100% - 32px)); }
.he-audio-host.is-mobile:not(.is-expanded) { left: calc(16px + env(safe-area-inset-left)); right: calc(16px + env(safe-area-inset-right)); width: auto; transform: none; }
.he-audio-host.is-mobile { bottom: calc(var(--he-nav-height) + env(safe-area-inset-bottom) + 8px); }
.he-audio-host.is-expanded { inset: 0; width: 100%; height: 100dvh; transform: none; z-index: 210; }
.he-audio-panel { height: 100%; padding-left: env(safe-area-inset-left); padding-right: env(safe-area-inset-right); }
.he-audio-header { padding-top: calc(12px + env(safe-area-inset-top)); }
.he-mini-player { position: relative; overflow: hidden; }
.he-mini-progress { position: absolute; bottom: 0; left: 0; height: 2px; background: rgb(var(--color-accent)); }
.he-has-mini .main-scroll-container { padding-bottom: 100px; }
@media (max-width: 899px) {
  .he-has-mini.he-compact-shell .main-scroll-container { padding-bottom: calc(var(--he-nav-height) + env(safe-area-inset-bottom) + 90px); }
  .he-has-mini .he-back-top { bottom: calc(var(--he-nav-height) + env(safe-area-inset-bottom) + 88px); }
}
</style>
