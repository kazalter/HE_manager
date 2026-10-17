<script setup lang="ts">
import UiSpinner from './UiSpinner.vue'
withDefaults(defineProps<{ label?: string; description?: string }>(), { label: '正在加载', description: '' })
</script>
<template>
  <div role="status" aria-live="polite" class="flex flex-col items-center justify-center gap-3 px-6 py-8 text-center text-muted">
    <UiSpinner :size="24" />
    <p class="text-body font-medium text-ink">{{ label }}</p>
    <p v-if="description" class="max-w-md text-meta text-subtle">{{ description }}</p>
  </div>
</template>
