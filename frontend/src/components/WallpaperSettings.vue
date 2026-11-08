<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { desktopBridge } from '../desktop'
import type { WallpaperState } from '../desktop-contract'
import { UiButton } from './ui'

const state = ref<WallpaperState>({ running: false, modelId: '', pauseWhenCovered: true, playing: null })
const error = ref('')
const busy = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | undefined
let editing = false
let revision = 0
let disposed = false
async function refresh() {
  if (editing) return
  const current = revision
  try { const result = await desktopBridge!.wallpaperState(); if (current === revision) state.value = result }
  catch (cause) { if (current === revision) error.value = cause instanceof Error ? cause.message : '无法读取壁纸状态' }
}
onMounted(async () => {
  await refresh()
  if (!disposed) refreshTimer = setInterval(() => { void refresh() }, 1500)
})
onBeforeUnmount(() => { disposed = true; ++revision; clearInterval(refreshTimer) })
async function preference(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  const current = ++revision
  editing = true
  try { const result = await desktopBridge!.wallpaperPreferences({ pauseWhenCovered: checked }); if (current === revision) { state.value = result; error.value = '' } }
  catch (cause) { if (current === revision) error.value = cause instanceof Error ? cause.message : '保存壁纸设置失败' }
  finally { if (current === revision) editing = false }
}
async function stop() {
  const current = ++revision
  editing = true; busy.value = true
  try { const result = await desktopBridge!.wallpaperStop(); if (current === revision) { state.value = result; error.value = '' } }
  catch (cause) { if (current === revision) error.value = cause instanceof Error ? cause.message : '停止壁纸失败' }
  finally { if (current === revision) { editing = false; busy.value = false } }
}
</script>
<template>
  <section class="space-y-3 rounded-2xl border border-line bg-surface-1 p-5" aria-labelledby="wallpaper-settings">
    <h2 id="wallpaper-settings" class="text-lg font-semibold">桌面壁纸</h2>
    <p class="text-body text-muted">在碧蓝航线页面选择皮肤并调整画面，然后选择“设为桌面壁纸”。关闭 HE Manager 后壁纸停止。</p>
    <label class="flex items-center gap-3 text-body"><input type="checkbox" :checked="state.pauseWhenCovered" :disabled="busy" @change="preference" />其他应用在前台时暂停壁纸</label>
    <p class="text-meta text-subtle">锁屏或电脑休眠时也会暂停；返回桌面后恢复。</p>
    <div class="flex items-center gap-3"><span class="text-body">{{ state.running ? `${state.modelId} · ${state.playing === null ? '正在加载' : state.playing ? '播放中' : '已暂停'}` : '壁纸未运行' }}</span><UiButton v-if="state.running" size="sm" :loading="busy" @click="stop">停止壁纸</UiButton></div>
    <p v-if="error" role="alert" class="text-body text-danger">{{ error }}</p>
  </section>
</template>
