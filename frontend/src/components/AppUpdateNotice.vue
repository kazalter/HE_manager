<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { RefreshCw, X } from 'lucide-vue-next'
import { audioPlaybackStore as audio } from '../stores/audioPlaybackStore'
const runningBuild = import.meta.env.HE_BUILD_ID as string | undefined
const availableBuild = ref('')
const dismissedBuild = ref('')
const videoPlaying = ref(false)
const offline = ref(!navigator.onLine)
const notice = computed(() => availableBuild.value && availableBuild.value !== dismissedBuild.value)
const playing = computed(() => audio.state.playing || videoPlaying.value)
let timer: number | undefined
let checking = false
let stopped = false
let controller: AbortController | null = null
const check = async () => {
  if (!runningBuild || checking || document.hidden || !navigator.onLine) return
  checking = true
  controller = new AbortController()
  const timeout = window.setTimeout(() => controller?.abort(), 5000)
  try {
    const response = await fetch('/version.json', { cache: 'no-store', signal: controller.signal })
    if (!response.ok) return
    const data = await response.json()
    if (!stopped && typeof data.buildId === 'string' && data.buildId !== runningBuild) availableBuild.value = data.buildId
  } catch { /* Disconnected servers must not interrupt reading or playback. */ }
  finally { window.clearTimeout(timeout); checking = false }
}
const onVisibility = () => { if (!document.hidden) void check() }
const onOnline = () => { offline.value = false; void check() }
const onOffline = () => { offline.value = true }
const onPlayback = () => { videoPlaying.value = Array.from(document.querySelectorAll('video')).some(video => !video.paused && !video.ended) }
const reload = () => { audio.stop(); window.location.reload() }
onMounted(() => {
  void check()
  timer = window.setInterval(() => { void check() }, 60000)
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('online', onOnline); window.addEventListener('offline', onOffline)
  document.addEventListener('play', onPlayback, true); document.addEventListener('pause', onPlayback, true); document.addEventListener('ended', onPlayback, true)
})
onBeforeUnmount(() => {
  stopped = true; controller?.abort(); window.clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisibility)
  window.removeEventListener('online', onOnline); window.removeEventListener('offline', onOffline)
  document.removeEventListener('play', onPlayback, true); document.removeEventListener('pause', onPlayback, true); document.removeEventListener('ended', onPlayback, true)
})
</script>
<template>
  <div v-if="offline" role="status" class="he-connection-notice">当前离线。已提交的下载会在服务器继续执行。</div>
  <aside v-if="notice" aria-label="网站更新" class="he-update-notice rounded-2xl border border-line-strong bg-surface-3 p-4 text-ink shadow-pop">
    <div class="flex items-start gap-3">
      <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-accent/15 text-accent" aria-hidden="true"><RefreshCw :size="18" /></span>
      <div class="min-w-0 flex-1 pt-0.5"><p class="text-body font-semibold">HE Manager 有新版本</p><p class="mt-0.5 text-meta text-subtle">{{ playing ? '更新会停止当前播放。' : '准备好后刷新，即可使用新版。' }}</p></div>
      <button type="button" class="-mr-1 -mt-1 grid min-h-11 min-w-11 place-items-center rounded-lg text-subtle transition-colors hover:bg-surface-2 hover:text-ink focus-ring" aria-label="暂不更新" @click="dismissedBuild = availableBuild"><X :size="18" aria-hidden="true" /></button>
    </div>
    <button type="button" class="mt-3 w-full min-h-11 rounded-lg bg-accent text-on-accent font-medium text-body transition-colors hover:bg-accent/90 focus-ring" @click="reload">{{ playing ? '停止播放并更新' : '刷新更新' }}</button>
  </aside>
</template>
<style scoped>
.he-update-notice { position: fixed; z-index: 260; right: 16px; bottom: 24px; width: min(360px, calc(100% - 32px)); }
.he-connection-notice { position: fixed; inset: calc(8px + env(safe-area-inset-top)) 16px auto; z-index: 270; margin-inline: auto; max-width: 480px; border: 1px solid rgb(var(--color-warning) / 0.3); border-radius: 10px; background: rgb(var(--color-surface-3)); box-shadow: var(--shadow-pop); padding: 10px 14px; text-align: center; color: rgb(var(--color-ink)); font-size: 0.8125rem; }
@media (max-width: 899px) { .he-update-notice { bottom: calc(var(--he-nav-height) + env(safe-area-inset-bottom) + 90px); } }
</style>
