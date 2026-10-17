<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Maximize, Pause, Play, SkipBack, SkipForward, Sparkles } from 'lucide-vue-next'
import { desktopBridge, desktopState, setDesktopPreferences, type DesktopPlayback, type VideoEnhancement } from '../../desktop'
import { UiButton, controlClass } from '../ui'
const props = defineProps<{ url: string; title: string; start: number }>()
const emit = defineEmits<{ progress: [position: number, duration: number, ended: boolean, force?: boolean] }>()
const state = ref<DesktopPlayback | null>(null), error = ref(''), busy = ref(false)
let loadedUrl = ''
let disposed = false, epoch = 0, timer: ReturnType<typeof setTimeout> | undefined
async function poll() {
 if (disposed) return
 try { state.value = await desktopBridge!.videoState(); if (state.value.running && !busy.value && loadedUrl === props.url) emit('progress', state.value.position, state.value.duration, state.value.ended) } catch { /* Retry status, without opening another player. */ }
 if (!disposed) timer = setTimeout(poll, 1000)
}
async function open() {
 const current = ++epoch; const requestedUrl = props.url; loadedUrl = ''; busy.value = true; error.value = ''
 try { const next = await desktopBridge!.openVideo({ url: props.url, title: props.title, start: props.start }); if (!disposed && epoch === current) { state.value = next; loadedUrl = requestedUrl } }
 catch (e: any) { if (!disposed && epoch === current) error.value = e.message }
 finally { if (epoch === current) busy.value = false }
}
async function control(action: 'pause' | 'seek' | 'fullscreen', value?: number) {
 try { await desktopBridge!.controlVideo(action, value); state.value = await desktopBridge!.videoState() } catch (e: any) { error.value = e.message }
}
async function mode(value: VideoEnhancement) {
 try { await setDesktopPreferences(value, desktopState.imageMode) } catch (e: any) { error.value = e.message }
}
watch(() => props.url, () => { void open() }, { immediate: true })
void poll()
onBeforeUnmount(() => {
 disposed = true; epoch++; clearTimeout(timer)
 if (state.value?.running && loadedUrl === props.url) emit('progress', state.value.position, state.value.duration, state.value.ended, true)
 void desktopBridge!.stopVideo()
})
const time = (seconds: number) => `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`
</script>
<template>
 <div class="relative flex min-h-0 flex-1 flex-col items-center justify-center gap-5 bg-background p-8 text-ink">
  <span class="grid size-16 place-items-center rounded-3xl bg-accent/10 text-accent"><Sparkles :size="28" /></span>
  <div class="max-w-lg text-center"><h2 class="text-heading font-semibold">本机 GPU 播放</h2><p class="mt-2 text-body text-muted">视频在独立播放器窗口中显示，超分由这台电脑处理。</p><p class="mt-2 text-meta text-subtle">{{ state?.hwdec ? `硬件解码：${state.hwdec}` : '正在连接本机播放器' }} · 累计掉帧 {{ state?.droppedFrames || 0 }}</p></div>
  <label class="w-full max-w-sm"><span class="mb-2 block text-meta text-muted">画面增强</span><select :value="desktopState.videoMode" :class="controlClass()" @change="mode(($event.target as HTMLSelectElement).value as VideoEnhancement)"><option value="off">原画／普通视频</option><option value="efficiency">Anime4K · 效率</option><option value="quality">Anime4K · 质量</option></select></label>
  <div v-if="state?.running" class="flex flex-wrap justify-center gap-2">
   <UiButton aria-label="后退十秒" @click="control('seek', -10)"><SkipBack :size="18" /></UiButton>
   <UiButton @click="control('pause')"><Play v-if="state.paused" :size="18" /><Pause v-else :size="18" />{{ state.paused ? '播放' : '暂停' }}</UiButton>
   <UiButton aria-label="前进十秒" @click="control('seek', 10)"><SkipForward :size="18" /></UiButton>
   <UiButton @click="control('fullscreen')"><Maximize :size="18" />全屏</UiButton>
  </div>
  <p v-if="state?.duration" class="text-meta tabular-nums text-muted">{{ time(state.position) }} / {{ time(state.duration) }}</p>
  <p v-if="error || state?.error" role="alert" class="max-w-lg text-center text-body text-danger">{{ error || state?.error }}</p>
  <UiButton v-if="!state?.running || error" :loading="busy" @click="open">{{ busy ? '正在启动' : '重新打开播放器' }}</UiButton>
 </div>
</template>
