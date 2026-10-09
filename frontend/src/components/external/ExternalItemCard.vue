<script setup lang="ts">
import type { Component } from 'vue'
import { Check, ExternalLink } from 'lucide-vue-next'

// Poster tile for a synced external favourite (WNACG / ASMR). Mirrors the
// MediaCard look: artwork tile with a hairline ring, title + meta below.
withDefaults(defineProps<{
  title: string
  cover?: string | null
  meta?: string
  /** Overlay badge text when not downloaded, e.g. an RJ code. */
  code?: string
  downloaded?: boolean
  aspect?: string
  placeholderIcon: Component
}>(), {
  cover: null,
  meta: '',
  code: '',
  downloaded: false,
  aspect: '2 / 3',
})
</script>

<template>
  <button type="button" class="tap-active group flex w-full min-w-0 flex-col rounded-2xl text-left focus:outline-none">
    <div
      class="relative w-full overflow-hidden rounded-2xl bg-surface-2 group-focus-visible:ring-2 group-focus-visible:ring-accent group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-background"
      :style="{ aspectRatio: aspect }"
    >
      <img
        v-if="cover"
        :src="cover"
        :alt="title"
        class="absolute inset-0 h-full w-full object-cover transition-transform duration-200 ease-out group-hover:scale-[1.03]"
        loading="eager"
        decoding="async"
      />
      <div v-else class="flex h-full w-full items-center justify-center text-faint">
        <component :is="placeholderIcon" :size="32" aria-hidden="true" />
      </div>
      <div class="pointer-events-none absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/8 transition-colors duration-200 group-hover:ring-white/20"></div>
      <span
        v-if="downloaded"
        class="absolute left-2 top-2 inline-flex h-6 items-center gap-1 rounded-md bg-success px-1.5 text-caption font-medium text-black/85"
      >
        <Check :size="12" aria-hidden="true" />已下载
      </span>
      <span
        v-else-if="code"
        class="absolute left-2 top-2 inline-flex h-6 max-w-[calc(100%-16px)] items-center truncate rounded-md bg-black/60 px-1.5 text-caption font-medium tabular-nums text-white/90"
      >
        {{ code }}
      </span>
    </div>
    <h3 class="mt-2.5 line-clamp-2 min-h-[2.75em] text-body font-medium leading-snug text-ink" :title="title">{{ title }}</h3>
    <div class="mt-1 flex min-w-0 items-center justify-between gap-2 text-meta text-subtle">
      <span class="truncate">{{ meta }}</span>
      <ExternalLink v-if="!downloaded" :size="14" class="shrink-0 transition-colors group-hover:text-ink" aria-hidden="true" />
    </div>
  </button>
</template>
