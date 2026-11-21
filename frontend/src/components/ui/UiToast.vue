<script setup lang="ts">
import { AlertCircle, CheckCircle2 } from 'lucide-vue-next'

withDefaults(defineProps<{ message: string; overlay?: boolean; urgent?: boolean }>(), { overlay: false, urgent: false })
</script>
<template>
  <div
    :role="urgent ? 'alert' : 'status'"
    :aria-live="urgent ? 'assertive' : 'polite'"
    class="inline-flex items-center gap-2 rounded-2xl squircle border px-4 py-2.5 text-body shadow-pop"
    :class="overlay
      ? 'border-white/15 bg-black/85 text-white backdrop-blur-md'
      : urgent
        ? 'border-danger/35 glass-elevated text-ink'
        : 'border-line-strong glass-elevated text-ink'"
  >
    <AlertCircle v-if="urgent" :size="16" class="shrink-0 text-danger" aria-hidden="true" />
    <CheckCircle2 v-else :size="16" class="shrink-0 text-accent" aria-hidden="true" />
    <span>{{ message }}</span>
  </div>
</template>
