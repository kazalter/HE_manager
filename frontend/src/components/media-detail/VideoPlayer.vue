<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{
  coverUrl: string
}>()

const emit = defineEmits<{
  ready: [container: HTMLDivElement | null]
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const compact = ref(false)
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  resizeObserver = new ResizeObserver(entries => {
    const { width, height } = entries[0].contentRect
    compact.value = width < 620 || height < 360
  })
  if (containerRef.value) resizeObserver.observe(containerRef.value)
  emit('ready', containerRef.value)
})
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  emit('ready', null)
})
</script>

<template>
  <div class="relative flex-1 min-h-0 bg-black overflow-hidden">
    <div v-if="props.coverUrl" class="absolute inset-0 pointer-events-none" aria-hidden="true">
      <img :src="props.coverUrl" class="w-full h-full object-cover scale-110 blur-3xl opacity-25" alt="" />
      <div class="absolute inset-0 bg-black/60"></div>
    </div>
    <div ref="containerRef" class="media-detail-player relative z-10 w-full h-full outline-none" :class="{ 'is-compact': compact }"></div>
  </div>
</template>

<style>
.media-detail-player .art-video-player {
  background-color: transparent !important;
}
.media-detail-player video { object-fit: contain !important; }
.media-detail-player.is-compact .art-control-pip,
.media-detail-player.is-compact .art-control-screenshot,
.media-detail-player.is-compact .art-control-setting,
.media-detail-player.is-compact .art-control-playMode { display: none !important; }
.media-detail-player.is-compact .art-video-player {
  --art-bottom-height: 72px;
  --art-control-height: 36px;
  --art-control-icon-size: 30px;
  --art-padding: 5px;
}
.media-detail-player.is-compact .art-bottom { padding-bottom: max(4px, env(safe-area-inset-bottom)) !important; }
.media-detail-player .art-notice {
  top: 50% !important;
  left: 50% !important;
  bottom: auto !important;
  right: auto !important;
  transform: translate(-50%, -50%) !important;
  pointer-events: none !important;
  z-index: 50 !important;
}

.media-detail-player .art-notice-inner {
  background: rgba(12, 12, 16, 0.88) !important;
  backdrop-filter: blur(20px) !important;
  -webkit-backdrop-filter: blur(20px) !important;
  border: 1px solid rgba(255, 255, 255, 0.18) !important;
  border-radius: 9999px !important;
  padding: 10px 24px !important;
  font-size: 14px !important;
  font-weight: 700 !important;
  color: #ffffff !important;
  box-shadow: 0 16px 36px -10px rgba(0, 0, 0, 0.8) !important;
  letter-spacing: 0.04em !important;
  text-align: center !important;
}
</style>
