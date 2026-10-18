<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { Camera, Maximize, Minimize, Pause, Play, Repeat1, RotateCcw, RotateCw, Settings2, Shuffle, SkipBack, SkipForward, ListVideo, Square, Volume2, VolumeX } from 'lucide-vue-next'
import { desktopBridge, desktopState, setDesktopPreferences, type DesktopPlayback, type DesktopVideoAction, type VideoEnhancement } from '../../desktop'
import { usePlayerChrome } from '../../composables/usePlayerChrome'
import { audioPlaybackStore } from '../../stores/audioPlaybackStore'
import { EmptyState, LoadingState, UiButton, UiIconButton, UiModal, UiSlider, UiToast, controlClass } from '../ui'
const props = defineProps<{ url: string; title: string; start: number; hasPrev?: boolean; hasNext?: boolean; playMode?: 'stop' | 'loop' | 'order' | 'shuffle'; headerActive?: boolean }>()
const emit = defineEmits<{
  progress: [position: number, duration: number, ended: boolean, force?: boolean, sourceUrl?: string]
  'cycle-mode': []
  'chrome': [visible: boolean]
  'fullscreen-change': [fullscreen: boolean]
  prev: []
  next: []
}>()
const canvasId = `he-video-${useId()}`
const state = ref<DesktopPlayback | null>(null), error = ref(''), busy = ref(false), settingsOpen = ref(false)
const actionError = ref('')
const seekValue = ref(0), dragging = ref(false), volume = ref(75)
const volumeDragging = ref(false)
const failure = computed(() => error.value || state.value?.error || '')
const controlsHovered = ref(false), keyboardFocus = ref(false)
const controlsElement = ref<HTMLElement | null>(null)
const held = computed(() => busy.value || !state.value?.running || !!state.value?.paused || !!failure.value || settingsOpen.value || dragging.value || volumeDragging.value || controlsHovered.value || keyboardFocus.value || !!props.headerActive)
const { visible: controlsVisible, reveal: revealControls } = usePlayerChrome(held)
const modeLabels = { stop: '播放完暂停', loop: '单片循环', order: '顺序播放', shuffle: '随机播放' }
const playModeLabel = computed(() => modeLabels[props.playMode || 'stop'])
const modeIcon = computed(() => ({ stop: Square, loop: Repeat1, order: ListVideo, shuffle: Shuffle }[props.playMode || 'stop']))
const enhancementLabel = computed(() => desktopState.videoMode === 'off' ? '原画' : desktopState.videoMode === 'quality' ? 'Anime4K · 质量' : 'Anime4K · 效率')
const pointerFocus = ref(false)
let previousVolume = 75, clickTimer: ReturnType<typeof setTimeout> | undefined
function onCanvasClick() {
 clearTimeout(clickTimer)
 clickTimer = setTimeout(() => { void control('pause') }, 240)
}
function onCanvasDoubleClick() { clearTimeout(clickTimer); void control('fullscreen') }
function onControlsFocus(event: FocusEvent) {
 const target = event.target as HTMLElement
 keyboardFocus.value = !pointerFocus.value && target.matches('input, select, :focus-visible')
 revealControls()
}
function onControlsBlur(event: FocusEvent) {
 if (!controlsElement.value?.contains(event.relatedTarget as Node | null)) keyboardFocus.value = false
}
function onPointerCancel() { dragging.value = false; volumeDragging.value = false }
async function mute() {
 if (volume.value > 0) { previousVolume = volume.value; await setVolume(0) }
 else await setVolume(previousVolume || 75)
}
function volumeWheel(event: WheelEvent) {
 if (!event.deltaY) return
 event.preventDefault()
 void setVolume(Math.min(100, Math.max(0, volume.value + (event.deltaY < 0 ? 5 : -5))))
}
function screenshot() {
 const canvas = document.getElementById(canvasId) as HTMLCanvasElement | null
 if (!canvas?.width || !state.value?.running) return
 try {
  canvas.toBlob(blob => {
   if (!blob || disposed) return
   const url = URL.createObjectURL(blob), link = document.createElement('a')
   link.href = url; link.download = 'HE-Manager-' + Math.floor(state.value?.position || 0) + 's.png'
   link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }, 'image/png')
 } catch { actionError.value = '截图失败，请重试。' }
}
watch(controlsVisible, visible => emit('chrome', visible), { immediate: true })
watch(() => state.value?.fullscreen || false, value => { emit('fullscreen-change', value); revealControls() })
const audioTracks = computed(() => state.value?.tracks.filter(track => track.type === 'audio') || [])
const subtitles = computed(() => state.value?.tracks.filter(track => track.type === 'sub') || [])
let loadedUrl = '', disposed = false, epoch = 0, timer: ReturnType<typeof setTimeout> | undefined
const time = (seconds: number) => {
 const value = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0
 const secondsText = (value % 60).toString().padStart(2, '0')
 return value >= 3600 ? Math.floor(value / 3600) + ':' + (Math.floor(value / 60) % 60).toString().padStart(2, '0') + ':' + secondsText : Math.floor(value / 60) + ':' + secondsText
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
   if (next.running && !busy.value && loadedUrl === props.url) emit('progress', next.position, next.duration, next.ended, false, url)
  }
 } catch { /* A transient IPC failure does not create a second player. */ }
 if (!disposed) timer = setTimeout(poll, 200)
}
function flushProgress() {
 if (state.value?.running && loadedUrl && !busy.value) emit('progress', state.value.position, state.value.duration, state.value.ended, true, loadedUrl)
}
async function captureFinalProgress() {
 const url = loadedUrl, generation = state.value?.generation
 if (!url || busy.value) return
 try {
  const latest = await desktopBridge!.videoState()
  if (!disposed && loadedUrl === url && latest.generation === generation && latest.running) {
   state.value = latest
   flushProgress()
  }
 } catch { flushProgress() }
}
async function restart() {
 await control('seek-to', 0)
 if (state.value?.paused || state.value?.ended) await control('pause')
}
defineExpose({ flushProgress, captureFinalProgress, revealControls, restart })
async function open() {
 flushProgress()
 const current = ++epoch, requestedUrl = props.url
 loadedUrl = ''; busy.value = true; error.value = ''; actionError.value = ''
 if (audioPlaybackStore.state.media) audioPlaybackStore.stop()
 void Promise.resolve(desktopBridge?.notifyAudioStop?.()).catch(() => {})
 try {
  const next = await desktopBridge!.openVideo({ url: requestedUrl, title: props.title, start: props.start })
  if (!disposed && epoch === current) { state.value = next; loadedUrl = requestedUrl; seekValue.value = next.position }
 } catch (failure: unknown) {
  if (!disposed && epoch === current) error.value = failure instanceof Error ? failure.message : '无法打开此视频，请重试。'
 } finally { if (!disposed && epoch === current) busy.value = false }
}
async function control(action: DesktopVideoAction, value?: number) {
 actionError.value = ''; revealControls()
 try {
  const next = action === 'pause' || action === 'fullscreen' || action === 'exit-fullscreen'
   ? await desktopBridge!.controlVideo(action) : await desktopBridge!.controlVideo(action, value ?? NaN)
  if (!disposed && loadedUrl === props.url && next.generation === state.value?.generation) {
   state.value = next
   if (action === 'pause') flushProgress()
  }
 }
 catch (failure: unknown) { actionError.value = failure instanceof Error ? failure.message : '播放操作失败，请重试。' }
}
async function seek(value: number) { dragging.value = false; await control('seek-to', value) }
async function setVolume(value: number) { volumeDragging.value = false; await control('volume', value); volume.value = state.value?.volume ?? value }
async function mode(value: VideoEnhancement) {
 actionError.value = ''
 try { await setDesktopPreferences(value, desktopState.imageMode) }
 catch (failure: unknown) { actionError.value = failure instanceof Error ? failure.message : '画面设置失败。' }
}
function onKeydown(event: KeyboardEvent) {
 pointerFocus.value = false
 if (event.key === 'Tab' && !controlsVisible.value) {
  event.preventDefault(); revealControls()
  void nextTick(() => {
   const controls = controlsElement.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled)')
   const target = event.shiftKey ? controls?.[controls.length - 1] : controls?.[0]
   target?.focus()
  })
  return
 }
 if (controlsElement.value?.contains(event.target as Node)) keyboardFocus.value = true
 if (event.ctrlKey || event.metaKey || event.altKey || (event.target as HTMLElement)?.closest('input, select, textarea, button, [contenteditable="true"]')) return
 const key = event.key.toLowerCase()
 if (key === ' ' || key === 'k') { event.preventDefault(); if (!event.repeat) void control('pause') }
 else if (key === 'f') { event.preventDefault(); if (!event.repeat) void control('fullscreen') }
 else if (key === 'm') { event.preventDefault(); if (!event.repeat) void mute() }
 else if (key === 'arrowup' || key === 'arrowdown') { event.preventDefault(); void setVolume(Math.max(0, Math.min(100, volume.value + (key === 'arrowup' ? 5 : -5)))) }
 else if (key === 'home') { event.preventDefault(); void seek(0) }
 else if (key === 'end') { event.preventDefault(); void seek(state.value?.duration || 0) }
 revealControls()
}
watch(() => props.url, () => { settingsOpen.value = false; controlsHovered.value = false; keyboardFocus.value = false; revealControls(); void open() }, { immediate: true })
onMounted(() => { desktopBridge!.mountVideoSurface(canvasId); void poll() })
onBeforeUnmount(() => {
 disposed = true; epoch++; clearTimeout(timer); clearTimeout(clickTimer)
 flushProgress()
 desktopBridge!.unmountVideoSurface()
 const generation = new URL(props.url, 'he://app').searchParams.get('he_session')
 void (generation ? desktopBridge!.stopVideo(generation) : desktopBridge!.stopVideo()).catch(() => {})
})
</script>
<template>
 <div class="desktop-video he-video-stage relative min-h-0 flex-1 overflow-hidden bg-black text-white" :class="{ 'chrome-hidden': !controlsVisible }" :data-controls-visible="controlsVisible" @mousemove="revealControls" @pointerdown.capture="pointerFocus = true; keyboardFocus = false; revealControls()" @keydown="onKeydown">
  <div class="absolute inset-0 bg-black">
   <canvas :id="canvasId" tabindex="0" :aria-label="title" class="absolute inset-0 h-full w-full focus-ring-inset" @click="onCanvasClick" @dblclick="onCanvasDoubleClick" />
   <UiToast v-if="actionError && !settingsOpen && !failure" :message="actionError" urgent overlay class="absolute bottom-28 left-1/2 z-40 max-w-[90%] -translate-x-1/2" />
   <div v-if="busy || state?.buffering" class="absolute inset-0 grid place-items-center bg-background/90">
    <LoadingState :label="busy ? '正在打开视频' : '正在缓冲'" description="准备好后将继续播放。" />
   </div>
   <div v-else-if="failure" class="absolute inset-0 grid place-items-center bg-background/95">
    <EmptyState title="视频暂时无法播放" :description="failure" tone="warning"><UiButton aria-label="重新打开视频" @click="open">重新打开</UiButton></EmptyState>
   </div>
  </div>
  <div ref="controlsElement" class="player-controls absolute inset-x-0 bottom-0 z-30 space-y-1 px-4 pb-3 pt-12 transition-[opacity,transform] duration-200" :class="{ 'opacity-0 translate-y-2 pointer-events-none': !controlsVisible }" :inert="!controlsVisible" @mouseenter="controlsHovered = true" @mouseleave="controlsHovered = false" @focusin="onControlsFocus" @focusout="onControlsBlur" @pointercancel="onPointerCancel">
   <UiSlider v-model="seekValue" label="播放位置" hide-label :max="state?.duration || 1" :step="0.1" :value-text="`${time(seekValue)} / ${time(state?.duration || 0)}`" :disabled="busy || !state?.duration" @pointerdown="dragging = true" @pointercancel="dragging = false" @commit="seek" />
   <div class="player-control-row flex min-w-0 items-center gap-1">
    <UiIconButton v-if="hasPrev !== undefined" label="上一项" :disabled="busy || !hasPrev" @click="$emit('prev')"><SkipBack :size="18" /></UiIconButton>
    <UiIconButton :label="state?.paused ? '播放' : '暂停'" :disabled="busy || !state?.running" @click="control('pause')"><Play v-if="state?.paused" :size="20" /><Pause v-else :size="20" /></UiIconButton>
    <UiIconButton v-if="hasNext !== undefined" label="下一项" :disabled="busy || !hasNext" @click="$emit('next')"><SkipForward :size="18" /></UiIconButton>
    <UiIconButton label="后退十秒" :disabled="busy" @click="control('seek', -10)"><RotateCcw :size="18" /></UiIconButton>
    <UiIconButton label="前进十秒" :disabled="busy" @click="control('seek', 10)"><RotateCw :size="18" /></UiIconButton>
    <div class="player-volume flex items-center" @wheel="volumeWheel">
     <UiIconButton :label="volume === 0 ? '取消静音' : '静音'" :disabled="busy" @click="mute"><VolumeX v-if="volume === 0" :size="19" /><Volume2 v-else :size="19" /></UiIconButton>
     <div class="player-volume-slider w-20"><UiSlider v-model="volume" label="音量" hide-label :value-text="volume + '%'" :disabled="busy" @pointerdown="volumeDragging = true" @pointercancel="volumeDragging = false" @commit="setVolume" /></div>
    </div>
    <span class="player-time min-w-0 flex-1 whitespace-nowrap px-2 text-meta tabular-nums text-white/80">{{ time(state?.position || 0) }} / {{ time(state?.duration || 0) }}</span>
    <UiIconButton :label="'播放模式：' + playModeLabel" @click="$emit('cycle-mode')"><component :is="modeIcon" :size="19" /></UiIconButton>
    <select aria-label="播放速度" title="播放速度" class="player-speed h-9 rounded-lg bg-transparent px-1 text-meta text-white focus-ring" :value="state?.speed || 1" :disabled="busy" @change="control('speed', Number(($event.target as HTMLSelectElement).value))"><option v-for="speed in [0.5, 0.75, 1, 1.25, 1.5, 2]" :key="speed" :value="speed">{{ speed }}×</option></select>
    <UiIconButton class="player-screenshot" label="保存视频截图" :disabled="busy || !state?.running" @click="screenshot"><Camera :size="19" /></UiIconButton>
    <UiIconButton label="播放设置" :title="'播放设置 · ' + enhancementLabel" :pressed="settingsOpen" @click="settingsOpen = true"><Settings2 :size="20" /></UiIconButton>
    <UiIconButton :label="state?.fullscreen ? '退出全屏' : '全屏'" :disabled="busy" @click="control('fullscreen')"><Minimize v-if="state?.fullscreen" :size="20" /><Maximize v-else :size="20" /></UiIconButton>
   </div>
  </div>
  <div v-if="!controlsVisible && state?.duration" class="pointer-events-none absolute inset-x-0 bottom-0 h-0.5 bg-white/15" aria-hidden="true"><div class="h-full bg-accent" :style="{ width: Math.min(100, Math.max(0, (state.position / state.duration) * 100)) + '%' }" /></div>
  <UiModal v-model:open="settingsOpen" title="播放设置" layer="viewer" size="sm" description="音轨、字幕和画面设置应用到当前播放会话。">
   <div class="space-y-5">
    <UiToast v-if="actionError" :message="actionError" urgent />
    <label class="block"><span class="mb-2 block text-meta text-muted">音轨</span><select :value="Number(state?.aid) || 0" :disabled="!audioTracks.length" :class="controlClass()" @change="control('audio-track', Number(($event.target as HTMLSelectElement).value))"><option v-if="!audioTracks.length" value="0">没有音轨</option><option v-for="track in audioTracks" :key="track.id" :value="track.id">{{ track.title || track.language || `音轨 ${track.id}` }}</option></select></label>
    <label class="block"><span class="mb-2 block text-meta text-muted">字幕</span><select :value="Number(state?.sid) || 0" :class="controlClass()" @change="control('subtitle-track', Number(($event.target as HTMLSelectElement).value))"><option value="0">关闭字幕</option><option v-for="track in subtitles" :key="track.id" :value="track.id">{{ track.title || track.language || `字幕 ${track.id}` }}</option></select></label>
    <label class="block"><span class="mb-2 block text-meta text-muted">播放速度</span><select :value="state?.speed || 1" :class="controlClass()" @change="control('speed', Number(($event.target as HTMLSelectElement).value))"><option v-for="speed in [0.5, 0.75, 1, 1.25, 1.5, 2]" :key="speed" :value="speed">{{ speed }}×</option></select></label>
    <label class="block"><span class="mb-2 block text-meta text-muted">画面比例</span><select aria-label="画面比例" :value="state?.aspectRatio || 0" :class="controlClass()" @change="control('aspect-ratio', Number(($event.target as HTMLSelectElement).value))"><option :value="0">原始比例</option><option :value="16 / 9">16:9</option><option :value="4 / 3">4:3</option></select></label>
    <label class="block"><span class="mb-2 block text-meta text-muted">画面增强</span><select aria-label="画面增强" :value="desktopState.videoMode" :class="controlClass()" @change="mode(($event.target as HTMLSelectElement).value as VideoEnhancement)"><option value="off">原画</option><option value="efficiency">Anime4K · 效率</option><option value="quality">Anime4K · 质量</option></select></label>
    <div><div class="mb-1 flex items-center gap-2 text-meta text-muted"><Volume2 :size="16" /><span>音量 {{ volume }}%</span></div><UiSlider v-model="volume" label="音量" hide-label :value-text="`${volume}%`" @pointerdown="volumeDragging = true" @pointercancel="volumeDragging = false" @commit="setVolume" /></div>
    <p class="text-caption text-subtle">{{ state?.hwdec ? '硬件解码已启用' : '正在读取解码状态' }}</p>
    <p class="text-caption text-subtle">空格 / K 播放暂停 · ← → 跳转十秒 · ↑ ↓ 音量 · M 静音 · F 全屏</p>
   </div>
  </UiModal>
 </div>
</template>

<style scoped>
.player-controls { background: linear-gradient(transparent, rgb(0 0 0 / .75) 55%, rgb(0 0 0 / .9)); }
.player-controls :deep(button) { color: rgb(255 255 255 / .85); }
.player-controls :deep(button:hover) { background: rgb(255 255 255 / .15); color: white; }
.player-controls :deep(.he-slider) { height: 22px; }
.player-speed option { color: white; background: #18181b; }
.chrome-hidden, .chrome-hidden canvas { cursor: none; }
@media (max-width: 1099px) {
 .player-volume-slider { display: none; }
 .player-control-row { flex-wrap: wrap; }
 .player-time { font-size: 12px; }
}
@media (prefers-reduced-motion: reduce) { .player-controls { transition: none; } }
</style>
