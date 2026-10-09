<script setup lang="ts">
withDefaults(defineProps<{ shape?: 'rect' | 'text' | 'circle' }>(), { shape: 'rect' })
</script>

<template>
  <div
    class="skeleton"
    :class="shape === 'circle' ? 'rounded-full' : shape === 'text' ? 'h-[0.85em] rounded-md' : 'rounded-lg'"
    aria-hidden="true"
  ></div>
</template>
