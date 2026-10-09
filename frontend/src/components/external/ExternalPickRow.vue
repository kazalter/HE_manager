<script setup lang="ts">
import type { Component } from 'vue'
import { ExternalLink } from 'lucide-vue-next'
import { UiBadge, iconButtonClass } from '../ui'

// One selectable row in a "下载选择" drawer (WNACG / ASMR).
withDefaults(defineProps<{
  title: string
  meta?: string
  cover?: string | null
  url: string
  checked: boolean
  downloaded?: boolean
  /** Thumb aspect: manga 2:3 covers, audio squares. */
  square?: boolean
  placeholderIcon: Component
}>(), {
  meta: '',
  cover: null,
  downloaded: false,
  square: false,
})

const emit = defineEmits<{ toggle: [] }>()
</script>

<template>
  <label
    class="flex min-h-14 items-center gap-3 px-4 py-3 transition-colors"
    :class="downloaded ? 'cursor-default' : 'cursor-pointer hover:bg-surface-2'"
  >
    <input
      type="checkbox"
      :checked="checked && !downloaded"
      :disabled="downloaded"
      class="size-4 shrink-0 rounded-sm accent-accent disabled:opacity-40"
      @change="emit('toggle')"
    />
    <div class="shrink-0 overflow-hidden rounded-lg bg-surface-2" :class="square ? 'size-12' : 'h-14 w-10'">
      <img v-if="cover" :src="cover" alt="" class="h-full w-full object-cover" loading="lazy" decoding="async" />
      <div v-else class="flex h-full w-full items-center justify-center text-faint">
        <component :is="placeholderIcon" :size="18" aria-hidden="true" />
      </div>
    </div>
    <div class="min-w-0 flex-1" :class="downloaded ? 'opacity-70' : ''">
      <p class="line-clamp-2 text-body font-medium leading-snug text-ink">{{ title }}</p>
      <div class="mt-0.5 flex min-w-0 items-center gap-2">
        <UiBadge v-if="downloaded" tone="success">已下载</UiBadge>
        <span class="truncate text-meta text-subtle">{{ meta }}</span>
      </div>
    </div>
    <a
      :href="url"
      target="_blank"
      rel="noreferrer"
      :class="iconButtonClass('ghost', 'sm')"
      aria-label="打开原站"
      title="打开原站"
      @click.stop
    >
      <ExternalLink :size="16" aria-hidden="true" />
    </a>
  </label>
</template>
