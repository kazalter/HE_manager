<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { Maximize, Minimize, Pause, Play, Settings2, SkipBack, SkipForward, Volume2 } from 'lucide-vue-next'
import { desktopBridge, desktopState, setDesktopPreferences, type DesktopPlayback, type DesktopVideoAction, type VideoEnhancement } from '../../desktop'
import { audioPlaybackStore } from '../../stores/audioPlaybackStore'
import { EmptyState, LoadingState, UiButton, UiIconButton, UiModal, UiSlider, UiToast, controlClass } from '../ui'
const props = defineProps<{ url: string; title: string; start: number }>()
const emit = defineEmits<{ progress: [position: number, duration: number, ended: boolean, force?: boolean] }>()
const canvasId = `he-video-${useId()}`
const state = ref<DesktopPlayback | null>(null), error = ref(''), busy = ref(false), settingsOpen = ref(false)
const actionError = ref('')
const seekValue = ref(0), dragging = ref(false), volume = ref(75)
const volumeDragging = ref(false)
const failure = computed(() => error.value || state.value?.error || '')
const audioTracks = computed(() => state.value?.tracks.filter(track => track.type === 'audio') || [])
const subtitles = computed(() => state.value?.tracks.filter(track => track.type === 'sub') || [])
let loadedUrl = '', disposed = false, epoch = 0, timer: ReturnType<typeof setTimeout> | undefined
const time = (seconds: number) => {
 const value = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0
 return `${Math.floor(value / 60)}:${(value % 60).toString().padStart(2, '0')}`
}
async function poll() {
 if (disposed) return
 const url = props.url
 try {
  const next = await desktopBridge!.videoState()
  if (!disposed && url === props.url && next.generation >= (state.value?.generation || 0)) {
   state.value = next
   if (!dragging.value) seekValue.value = next.position
   if (!volumeDragging.value) volume.value = next.volume
   if (next.running && !busy.value && loadedUrl === props.url) emit('progress', next.position, next.duration, next.ended)
  }
 } catch { /* A transient IPC failure does not create a second player. */ }
 if (!disposed) timer = setTimeout(poll, 200)
}
async function open() {
 const current = ++epoch, requestedUrl = props.url
 loadedUrl = ''; busy.value = true; error.value = ''; actionError.value = ''
 if (audioPlaybackStore.state.playing) audioPlaybackStore.togglePlay()
 try {
  const next = await desktopBridge!.openVideo({ url: requestedUrl, title: props.title, start: props.start })
  if (!disposed && epoch === current) { state.value = next; loadedUrl = requestedUrl; seekValue.value = next.position }
 } catch (failure: unknown) {
  if (!disposed && epoch === current) error.value = failure instanceof Error ? failure.message : '无法打开此视频，请重试。'
 } finally { if (!disposed && epoch === current) busy.value = false }
}
async function control(action: DesktopVideoAction, value?: number) {
 actionError.value = ''
 try {
  if (action === 'pause' || action === 'fullscreen' || action === 'exit-fullscreen') await desktopBridge!.controlVideo(action)
  else await desktopBridge!.controlVideo(action, value ?? NaN)
 }
 catch (failure: unknown) { actionError.value = failure instanceof Error ? failure.message : '播放操作失败，请重试。' }
}
async function seek(value: number) { dragging.value = false; await control('seek-to', value) }
async function setVolume(value: number) { volumeDragging.value = false; await control('volume', value) }
async function mode(value: VideoEnhancement) {
 actionError.value = ''
 try { await setDesktopPreferences(value, desktopState.imageMode) }
 catch (failure: unknown) { actionError.value = failure instanceof Error ? failure.message : '画面设置失败。' }
}
function onKeydown(event: KeyboardEvent) {
 if (event.key === 'F11') { event.preventDefault(); void control('fullscreen') }
 if ((event.key === ' ' || event.key.toLowerCase() === 'k') && event.target instanceof HTMLCanvasElement) {
  event.preventDefault(); void control('pause')
 }
}
watch(() => props.url, () => { settingsOpen.value = false; void open() }, { immediate: true })
onMounted(() => { desktopBridge!.mountVideoSurface(canvasId); void poll() })
onBeforeUnmount(() => {
 disposed = true; epoch++; clearTimeout(timer)
 if (state.value?.running && loadedUrl === props.url) emit('progress', state.value.position, state.value.duration, state.value.ended, true)
 desktopBridge!.unmountVideoSurface()
 void desktopBridge!.stopVideo().catch(() => {})
})
</script>
<template>
 <div class="desktop-video flex min-h-0 flex-1 flex-col bg-background text-ink" @keydown="onKeydown">
  <div class="relative min-h-0 flex-1 bg-black">
   <canvas :id="canvasId" tabindex="0" :aria-label="title" class="absolute inset-0 h-full w-full focus-ring-inset" @click="control('pause')" @dblclick="control('fullscreen')" />
   <UiToast v-if="actionError && !settingsOpen && !failure" :message="actionError" urgent overlay class="absolute bottom-4 left-1/2 z-20 max-w-[90%] -translate-x-1/2" />
   <div v-if="busy || state?.buffering" class="absolute inset-0 grid place-items-center bg-background/90">
    <LoadingState :label="busy ? '正在打开视频' : '正在缓冲'" description="准备好后将继续播放。" />
   </div>
   <div v-else-if="failure" class="absolute inset-0 grid place-items-center bg-background/95">
    <EmptyState title="视频暂时无法播放" :description="failure" tone="warning"><UiButton @click="open">重新打开</UiButton></EmptyState>
   </div>
  </div>
  <div class="shrink-0 space-y-1 border-t border-line bg-surface px-4 pb-3 pt-2">
   <UiSlider v-model="seekValue" label="播放位置" hide-label :max="state?.duration || 1" :step="0.1" :value-text="`${time(seekValue)} / ${time(state?.duration || 0)}`" :disabled="busy || !state?.duration" @pointerdown="dragging = true" @pointercancel="dragging = false" @commit="seek" />
   <div class="flex min-w-0 items-center gap-2">
    <UiIconButton :label="state?.paused ? '播放' : '暂停'" :disabled="busy || !state?.running" @click="control('pause')"><Play v-if="state?.paused" :size="20" /><Pause v-else :size="20" /></UiIconButton>
    <UiIconButton label="后退十秒" :disabled="busy" @click="control('seek', -10)"><SkipBack :size="18" /></UiIconButton>
    <UiIconButton label="前进十秒" :disabled="busy" @click="control('seek', 10)"><SkipForward :size="18" /></UiIconButton>
    <span class="min-w-0 flex-1 truncate text-meta tabular-nums text-muted">{{ time(state?.position || 0) }} / {{ time(state?.duration || 0) }}</span>
    <span class="hidden text-meta text-subtle lg:block">{{ desktopState.videoMode === 'off' ? '原画' : desktopState.videoMode === 'quality' ? 'Anime4K · 质量' : 'Anime4K · 效率' }}</span>
    <UiIconButton label="播放设置" :pressed="settingsOpen" @click="settingsOpen = true"><Settings2 :size="20" /></UiIconButton>
    <UiIconButton :label="state?.fullscreen ? '退出全屏' : '全屏'" :disabled="busy" @click="control('fullscreen')"><Minimize v-if="state?.fullscreen" :size="20" /><Maximize v-else :size="20" /></UiIconButton>
   </div>
  </div>
  <UiModal v-model:open="settingsOpen" title="播放设置" layer="viewer" size="sm" description="音轨、字幕和画面设置应用到当前播放会话。">
   <div class="space-y-5">
    <UiToast v-if="actionError" :message="actionError" urgent />
    <label class="block"><span class="mb-2 block text-meta text-muted">音轨</span><select :value="Number(state?.aid) || 0" :disabled="!audioTracks.length" :class="controlClass()" @change="control('audio-track', Number(($event.target as HTMLSelectElement).value))"><option v-if="!audioTracks.length" value="0">没有音轨</option><option v-for="track in audioTracks" :key="track.id" :value="track.id">{{ track.title || track.language || `音轨 ${track.id}` }}</option></select></label>
    <label class="block"><span class="mb-2 block text-meta text-muted">字幕</span><select :value="Number(state?.sid) || 0" :class="controlClass()" @change="control('subtitle-track', Number(($event.target as HTMLSelectElement).value))"><option value="0">关闭字幕</option><option v-for="track in subtitles" :key="track.id" :value="track.id">{{ track.title || track.language || `字幕 ${track.id}` }}</option></select></label>
    <label class="block"><span class="mb-2 block text-meta text-muted">播放速度</span><select :value="state?.speed || 1" :class="controlClass()" @change="control('speed', Number(($event.target as HTMLSelectElement).value))"><option v-for="speed in [0.5, 0.75, 1, 1.25, 1.5, 2]" :key="speed" :value="speed">{{ speed }}×</option></select></label>
    <label class="block"><span class="mb-2 block text-meta text-muted">画面增强</span><select :value="desktopState.videoMode" :class="controlClass()" @change="mode(($event.target as HTMLSelectElement).value as VideoEnhancement)"><option value="off">原画</option><option value="efficiency">Anime4K · 效率</option><option value="quality">Anime4K · 质量</option></select></label>
    <div><div class="mb-1 flex items-center gap-2 text-meta text-muted"><Volume2 :size="16" /><span>音量 {{ volume }}%</span></div><UiSlider v-model="volume" label="音量" hide-label :value-text="`${volume}%`" @pointerdown="volumeDragging = true" @pointercancel="volumeDragging = false" @commit="setVolume" /></div>
    <p class="text-caption text-subtle">{{ state?.hwdec ? '硬件解码已启用' : '正在读取解码状态' }}</p>
   </div>
  </UiModal>
 </div>
</template>
