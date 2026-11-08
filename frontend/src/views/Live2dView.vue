<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { desktopBridge, desktopSession, desktopState } from '../desktop'

const viewer = ref<HTMLIFrameElement | null>(null)
const immersive = ref(false)
const selectedModel = ref('')
const wallpaperBusy = ref(false)
const wallpaperMessage = ref('')

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
  try {
    await desktopBridge.wallpaperStart(selectedModel.value)
    wallpaperMessage.value = '已设置为桌面壁纸，可在设置中停止或调整省电选项。'
  } catch (error) { wallpaperMessage.value = error instanceof Error ? error.message : '无法设置壁纸' }
  finally { wallpaperBusy.value = false }
}

onMounted(() => window.addEventListener('message', onViewerMessage))
onBeforeUnmount(() => {
  window.removeEventListener('message', onViewerMessage)
  document.body.classList.remove('he-l2d-immersive')
})
</script>

<template>
  <section class="live2d-view" :class="{ immersive }">
    <iframe :key="desktopSession.generation" ref="viewer" src="/l2d/" title="碧蓝航线 Live2D 皮肤查看器" allow="fullscreen" allowfullscreen></iframe>
    <div v-if="desktopBridge && desktopState.platform === 'win32' && !immersive" class="wallpaper-action">
      <button type="button" :disabled="!selectedModel || wallpaperBusy" @click="setWallpaper">{{ wallpaperBusy ? '正在设置…' : '设为桌面壁纸' }}</button>
      <span v-if="wallpaperMessage" role="status">{{ wallpaperMessage }}</span>
    </div>
  </section>
</template>

<style scoped>
.live2d-view { height: 100%; min-height: 0; position: relative; }
.live2d-view.immersive { height: 100dvh; min-height: 0; }
iframe { width: 100%; height: 100%; border: 0; background: #101014; display: block; }
.wallpaper-action { position: absolute; top: 12px; right: 12px; display: flex; align-items: flex-end; flex-direction: column; gap: 6px; color: white; font-size: 13px; }
.wallpaper-action button, .wallpaper-action span { border: 1px solid #555; border-radius: 8px; background: #19191fee; padding: 8px 12px; }
.wallpaper-action button:disabled { opacity: .5; }
:global(body.he-l2d-immersive #he-main-content) {
  position: fixed; inset: 0; z-index: 2147483000; width: 100vw; height: 100dvh !important; overflow: hidden !important;
}
</style>
