<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { desktopBridge } from '../desktop'
import type { WallpaperPreferencesPatch, WallpaperState } from '../desktop-contract'
import { UiButton } from './ui'

const state = ref<WallpaperState>({
  running: false,
  modelId: '',
  pauseWhenCovered: true,
  muted: true,
  keepInTray: true,
  autoRestore: true,
  displayId: null,
  displays: [],
  playing: null,
})
const modelNames = ref<Record<string, string>>({})
const error = ref('')
const busy = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | undefined
let unsubscribeWallpaper: (() => void) | undefined
let editing = false
let revision = 0
let disposed = false

const modelDisplayName = computed(() => {
  const id = state.value.modelId
  if (!id) return ''
  const name = modelNames.value[id]
  return name && name !== id ? `${name} (${id})` : id
})

async function loadModelNames() {
  try {
    const response = await fetch('/l2d/models/manifest.json')
    if (!response.ok) return
    const list = await response.json()
    if (!Array.isArray(list)) return
    const map: Record<string, string> = {}
    for (const item of list) {
      if (item && typeof item.id === 'string' && typeof item.name === 'string') {
        map[item.id] = item.name
      }
    }
    if (!disposed) modelNames.value = map
  } catch {}
}

async function refresh() {
  if (editing) return
  const current = revision
  try { const result = await desktopBridge!.wallpaperState(); if (current === revision) state.value = result }
  catch (cause) { if (current === revision) error.value = cause instanceof Error ? cause.message : '无法读取壁纸状态' }
}
onMounted(async () => {
  void loadModelNames()
  await refresh()
  unsubscribeWallpaper = desktopBridge!.onWallpaperChanged?.((next) => {
    if (!editing) state.value = next
  })
  if (!disposed) refreshTimer = setInterval(() => { void refresh() }, 1500)
})
onBeforeUnmount(() => {
  disposed = true
  ++revision
  clearInterval(refreshTimer)
  unsubscribeWallpaper?.()
})
async function updatePreference(patch: WallpaperPreferencesPatch) {
  const current = ++revision
  editing = true
  try {
    const result = await desktopBridge!.wallpaperPreferences(patch)
    if (current === revision) {
      state.value = { ...result, displays: result.displays ?? state.value.displays }
      error.value = ''
    }
  }
  catch (cause) { if (current === revision) error.value = cause instanceof Error ? cause.message : '保存壁纸设置失败' }
  finally { if (current === revision) editing = false }
}
function preference(event: Event) {
  return updatePreference({ pauseWhenCovered: (event.target as HTMLInputElement).checked })
}
function onDisplayChange(event: Event) {
  const raw = (event.target as HTMLSelectElement).value
  return updatePreference({ displayId: raw ? Number(raw) : null })
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
    <p class="text-body text-muted">在碧蓝航线页面选择皮肤并调整画面，然后选择“设为壁纸”。</p>
    <label class="flex items-center gap-3 text-body"><input type="checkbox" :checked="state.pauseWhenCovered" :disabled="busy" @change="preference" />其他应用在前台时暂停壁纸</label>
    <label class="flex items-center gap-3 text-body"><input type="checkbox" :checked="state.muted !== false" :disabled="busy" @change="updatePreference({ muted: ($event.target as HTMLInputElement).checked })" />壁纸静音</label>
    <label class="flex items-center gap-3 text-body"><input type="checkbox" :checked="state.keepInTray !== false" :disabled="busy" @change="updatePreference({ keepInTray: ($event.target as HTMLInputElement).checked })" />关闭主窗口时最小化到系统托盘并保持壁纸运行</label>
    <label class="flex items-center gap-3 text-body"><input type="checkbox" :checked="state.autoRestore !== false" :disabled="busy" @change="updatePreference({ autoRestore: ($event.target as HTMLInputElement).checked })" />启动 HE Manager 时自动恢复上次壁纸</label>
    <label v-if="(state.displays?.length ?? 0) > 1" class="flex items-center gap-3 text-body">
      <span>目标显示器</span>
      <select class="rounded-lg border border-line bg-surface-2 px-2.5 py-1 text-body" :value="state.displayId ?? ''" :disabled="busy" @change="onDisplayChange">
        <option v-for="d in state.displays" :key="d.id" :value="d.id">{{ d.label }} ({{ d.width }}×{{ d.height }}){{ d.primary ? ' · 主显示器' : '' }}</option>
      </select>
    </label>
    <p class="text-meta text-subtle">锁屏或电脑休眠时也会自动暂停；返回桌面后恢复。</p>
    <div class="flex items-center gap-3"><span class="text-body">{{ state.running ? `${modelDisplayName} · ${state.playing === null ? '正在加载' : state.playing ? '播放中' : '已暂停'}` : '壁纸未运行' }}</span><UiButton v-if="state.running" size="sm" :loading="busy" @click="stop">停止壁纸</UiButton></div>
    <p v-if="error" role="alert" class="text-body text-danger">{{ error }}</p>
  </section>
</template>
