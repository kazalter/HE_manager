<script setup lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import type { Media } from '../../types'

defineProps<{
  media: Media
  imageUrl: string
  showControls: boolean
  clickOnlyControls: boolean
}>()

const emit = defineEmits<{
  previous: []
  next: []
  viewerClick: []
  viewerDoubleClick: []
}>()
</script>

<template>
  <div
    class="flex-1 min-h-0 flex flex-col items-center bg-black overflow-hidden relative group"
    @click="emit('viewerClick')"
    @dblclick="emit('viewerDoubleClick')"
  >
    <div class="flex-1 flex items-center justify-center w-full h-full relative">
      <button
        @click.stop="emit('previous')"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 -translate-x-6 pointer-events-none'
            : 'opacity-0 -translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="absolute left-5 z-10 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300"
        title="上一项"
      >
        <ChevronLeft :size="34" class="mx-auto" />
      </button>

      <img :src="imageUrl" class="h-full w-full object-contain transition-opacity duration-300 cursor-zoom-in" :alt="media.title" />

      <button
        @click.stop="emit('next')"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 translate-x-6 pointer-events-none'
            : 'opacity-0 translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="absolute right-5 z-10 w-14 h-14 rounded-2xl bg-black/45 backdrop-blur-md text-white/55 hover:text-white hover:bg-black/70 transition-all duration-300"
        title="下一项"
      >
        <ChevronRight :size="34" class="mx-auto" />
      </button>
    </div>
  </div>
</template>
