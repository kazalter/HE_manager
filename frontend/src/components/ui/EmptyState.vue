<script setup lang="ts">
import type { Component } from 'vue'

withDefaults(defineProps<{
  title: string
  description?: string
  icon?: Component
  tone?: 'neutral' | 'warning' | 'danger'
  /** Less vertical padding, for empty panels inside cards. */
  compact?: boolean
}>(), {
  description: '',
  icon: undefined,
  tone: 'neutral',
  compact: false,
})
</script>

<template>
  <div class="flex flex-col items-center justify-center px-6 text-center" :class="compact ? 'py-10' : 'py-20'">
    <div
      v-if="icon || $slots.icon"
      class="mb-4 grid size-12 place-items-center rounded-2xl border"
      :class="{
        'border-line bg-surface-2 text-subtle': tone === 'neutral',
        'border-warning/25 bg-warning/10 text-warning': tone === 'warning',
        'border-danger/25 bg-danger/10 text-danger': tone === 'danger',
      }"
      aria-hidden="true"
    >
      <slot name="icon"><component :is="icon" :size="22" /></slot>
    </div>
    <p class="text-heading font-semibold text-ink">{{ title }}</p>
    <p v-if="description || $slots.description" class="mt-1.5 max-w-md text-meta text-subtle">
      <slot name="description">{{ description }}</slot>
    </p>
    <div v-if="$slots.default" class="mt-5 flex flex-wrap items-center justify-center gap-2">
      <slot />
    </div>
  </div>
</template>
