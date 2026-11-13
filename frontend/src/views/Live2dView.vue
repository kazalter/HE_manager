<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Check, ChevronDown, CircleAlert, Download, LoaderCircle, Monitor, X } from 'lucide-vue-next'
import { desktopBridge, desktopSession, desktopState } from '../desktop'
import type { L2dUpdateState } from '../desktop-contract'

const viewer = ref<HTMLIFrameElement | null>(null)
const immersive = ref(false)
const selectedModel = ref('')
const wallpaperBusy = ref(false)
const wallpaperMessage = ref('')
const update = ref<L2dUpdateState>({ running: false, message: '', failures: [] })
const viewerRevision = ref(0)
const updateOpen = ref(false)
const wallpaperOpen = ref(false)
const dismissedKey = 'he-l2d-update-dismissed'
let firstUpdateRead = true
let startError = false
let timer: ReturnType<typeof setInterval> | undefined

async function refreshUpdate() {
  if (!desktopBridge?.l2dUpdateStatus || startError) return
  const wasRunning = update.value.running
  update.value = await desktopBridge.l2dUpdateStatus()
  if (firstUpdateRead && update.value.running && sessionStorage.getItem(dismissedKey) !== '1') updateOpen.value = true
  firstUpdateRead = false
  if (wasRunning && !update.value.running) viewerRevision.value++
}
async function startUpdate() {
  if (!desktopBridge?.l2dUpdateStart) return
  startError = false
  updateOpen.value = true
  sessionStorage.removeItem(dismissedKey)
  try { update.value = await desktopBridge.l2dUpdateStart() }
  catch (error) { startError = true; update.value = { running: false, message: `更新失败：${error instanceof Error ? error.message : '无法开始更新'}`, failures: [] } }
}
function closeUpdate() { updateOpen.value = false; sessionStorage.setItem(dismissedKey, '1') }
function showUpdate() { updateOpen.value = true; sessionStorage.removeItem(dismissedKey) }

function onViewerMessage(event: MessageEvent) {
  if (event.origin !== window.location.origin || event.source !== viewer.value?.contentWindow) return
  if (event.data?.type === 'l2d:model' && typeof event.data.id === 'string') selectedModel.value = event.data.id
  if (event.data?.type === 'l2d:immersive') {
    immersive.value = event.data.active === true
    document.body.classList.toggle('he-l2d-immersive', immersive.value)
  }
}

async function setWallpaper() {
  if (!desktopBridge || !selectedModel.value) return
  wallpaperBusy.value = true; wallpaperMessage.value = ''
  wallpaperOpen.value = true
  try {
    await desktopBridge.wallpaperStart(selectedModel.value)
    wallpaperMessage.value = '已设置为桌面壁纸，可在设置中停止或调整省电选项。'
  } catch (error) { wallpaperMessage.value = error instanceof Error ? error.message : '无法设置壁纸' }
  finally { wallpaperBusy.value = false }
}

onMounted(() => {
  window.addEventListener('message', onViewerMessage)
  if (desktopBridge && desktopState.platform === 'win32') {
    void refreshUpdate().catch(() => {})
    timer = setInterval(() => { void refreshUpdate().catch(() => {}) }, 1500)
  }
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  window.removeEventListener('message', onViewerMessage)
  document.body.classList.remove('he-l2d-immersive')
})
</script>

<template>
  <section class="live2d-view" :class="{ immersive }">
    <iframe :key="desktopSession.generation + ':' + viewerRevision" ref="viewer" src="/l2d/" title="碧蓝航线 Live2D 皮肤查看器" allow="fullscreen" allowfullscreen></iframe>
    <div v-if="desktopBridge && desktopState.platform === 'win32' && !immersive" class="viewer-actions">
      <div class="action-row">
        <button class="action secondary" type="button" :disabled="!selectedModel || wallpaperBusy" @click="setWallpaper"><Monitor :size="16" />{{ wallpaperBusy ? '正在设置' : '设为壁纸' }}</button>
        <button v-if="desktopBridge.l2dUpdateStart && !update.running" class="action primary" type="button" @click="startUpdate"><Download :size="16" />继续解包</button>
        <button v-else-if="desktopBridge.l2dUpdateStart" class="action primary" type="button" @click="showUpdate"><LoaderCircle :size="16" class="spin" />查看进度</button>
        <button v-if="!update.running && update.message && !updateOpen" class="action icon-action" type="button" aria-label="查看解包结果" title="查看解包结果" @click="showUpdate"><ChevronDown :size="16" /></button>
      </div>
      <section v-if="updateOpen" class="notice" aria-label="解包状态" role="status">
        <div class="notice-head">
          <span class="notice-icon" :class="{ warning: update.failures.length || update.message.startsWith('更新失败') }"><LoaderCircle v-if="update.running" :size="16" class="spin" /><CircleAlert v-else-if="update.failures.length || update.message.startsWith('更新失败')" :size="16" /><Check v-else :size="16" /></span>
          <div><strong>{{ update.running ? '正在更新图鉴' : '解包结果' }}</strong><p>{{ update.running ? '可以关闭此面板，任务会继续进行' : '已有皮肤会自动跳过' }}</p></div>
          <button class="close" type="button" aria-label="关闭解包提示" @click="closeUpdate"><X :size="17" /></button>
        </div>
        <p class="notice-message">{{ update.message || '正在准备…' }}</p>
        <details v-if="update.failures.length" class="failure-list"><summary>查看 {{ update.failures.length }} 项失败详情</summary><ul><li v-for="failure in update.failures" :key="failure.id"><strong>{{ failure.id }}</strong><span>{{ failure.error }}</span></li></ul></details>
      </section>
      <section v-if="wallpaperOpen && wallpaperMessage" class="notice wallpaper-notice" role="status"><p>{{ wallpaperMessage }}</p><button class="close" type="button" aria-label="关闭壁纸提示" @click="wallpaperOpen = false"><X :size="17" /></button></section>
    </div>
  </section>
</template>

<style scoped>
.live2d-view { height: 100%; min-height: 0; position: relative; }
.live2d-view.immersive { height: 100dvh; min-height: 0; }
iframe { width: 100%; height: 100%; border: 0; background: #101014; display: block; }
.viewer-actions { position: absolute; z-index: 20; top: 16px; right: 18px; display: flex; align-items: flex-end; flex-direction: column; gap: 10px; color: #f1f0f7; font: 13px/1.5 system-ui, sans-serif; max-width: calc(100% - 36px); }
.action-row { display: flex; gap: 8px; }
.action, .close { display: inline-flex; align-items: center; justify-content: center; gap: 7px; cursor: pointer; }
.action { min-height: 38px; border: 1px solid #ffffff20; border-radius: 10px; padding: 0 13px; font-weight: 600; color: #e9e8ef; box-shadow: 0 6px 24px #0003; }
.secondary, .icon-action { background: #1a1b25ed; }
.primary { background: #6a61d8; border-color: #8178ef; color: white; }
.action:hover { filter: brightness(1.16); } .action:disabled { opacity: .45; cursor: default; filter: none; }
.icon-action { padding: 0 10px; }
.notice { width: min(360px, calc(100vw - 36px)); max-height: min(50vh, 390px); overflow: auto; padding: 15px; border: 1px solid #ffffff1b; border-radius: 14px; background: #1a1b26f5; box-shadow: 0 14px 42px #0007; backdrop-filter: blur(16px); }
.notice-head { display: flex; align-items: flex-start; gap: 10px; }
.notice-head strong { font-size: 14px; } .notice-head p { margin: 2px 0 0; color: #aaa9bb; font-size: 12px; }
.notice-icon { display: grid; place-items: center; width: 30px; height: 30px; flex: none; border-radius: 9px; color: #b3aaff; background: #8276e92a; }
.notice-icon.warning { color: #ffc587; background: #d9943828; }
.close { margin-left: auto; padding: 5px; border: 0; border-radius: 7px; background: transparent; color: #aaa9bb; }
.close:hover { color: white; background: #ffffff16; }
.notice-message { margin: 12px 0 0; padding: 10px 11px; border-radius: 9px; background: #ffffff0a; color: #dddce8; overflow-wrap: anywhere; }
.failure-list { margin-top: 10px; color: #f0c49a; } .failure-list summary { cursor: pointer; } .failure-list ul { margin: 8px 0 0; padding: 0; list-style: none; }
.failure-list li { padding: 8px 0; border-top: 1px solid #ffffff12; overflow-wrap: anywhere; } .failure-list li strong, .failure-list li span { display: block; } .failure-list li span { color: #b9b5c5; white-space: pre-wrap; }
.wallpaper-notice { display: flex; gap: 8px; align-items: flex-start; } .wallpaper-notice p { margin: 0; }
.spin { animation: spin 1s linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spin { animation: none; } }
:global(body.he-l2d-immersive #he-main-content) {
  position: fixed; inset: 0; z-index: 2147483000; width: 100vw; height: 100dvh !important; overflow: hidden !important;
}
</style>
