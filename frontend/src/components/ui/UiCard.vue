<script setup lang="ts">
import type { Component } from 'vue'
import { cardClass, type CardPadding } from './classes'

withDefaults(defineProps<{
  as?: string | Component
  padding?: CardPadding
  /** Hover/focus styles for clickable cards (use with as="button" or a link). */
  interactive?: boolean
}>(), {
  as: 'div',
  padding: 'md',
  interactive: false,
})
</script>

<template>
  <component :is="as" :class="cardClass(padding, interactive)">
    <slot />
  </component>
</template>
