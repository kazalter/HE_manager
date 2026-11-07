<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { desktopSession } from '../desktop'

const viewer = ref<HTMLIFrameElement | null>(null)
const immersive = ref(false)

function onViewerMessage(event: MessageEvent) {
  if (event.origin !== window.location.origin || event.source !== viewer.value?.contentWindow || event.data?.type !== 'l2d:immersive') return
  immersive.value = event.data.active === true
  document.body.classList.toggle('he-l2d-immersive', immersive.value)
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
  </section>
</template>

<style scoped>
.live2d-view { height: calc(100dvh - 4rem); min-height: 500px; }
.live2d-view.immersive { height: 100dvh; min-height: 0; }
iframe { width: 100%; height: 100%; border: 0; background: #101014; display: block; }
:global(body.he-l2d-immersive #he-main-content) {
  position: fixed; inset: 0; z-index: 2147483000; width: 100vw; height: 100dvh !important; overflow: hidden !important;
}
</style>
