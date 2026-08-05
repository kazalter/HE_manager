<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{
  coverUrl: string
}>()

const emit = defineEmits<{
  ready: [container: HTMLDivElement | null]
}>()

const containerRef = ref<HTMLDivElement | null>(null)

onMounted(() => emit('ready', containerRef.value))
onBeforeUnmount(() => emit('ready', null))
</script>

<template>
  <div class="relative flex-1 min-h-0 bg-black overflow-hidden">
    <div v-if="props.coverUrl" class="absolute inset-0 pointer-events-none" aria-hidden="true">
      <img :src="props.coverUrl" class="w-full h-full object-cover scale-110 blur-3xl opacity-25" alt="" />
      <div class="absolute inset-0 bg-black/60"></div>
    </div>
    <div ref="containerRef" class="media-detail-player relative z-10 w-full h-full outline-none"></div>
  </div>
</template>

<style>
.media-detail-player .art-video-player {
  background-color: transparent !important;
}
</style>
