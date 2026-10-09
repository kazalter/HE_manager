<script setup lang="ts">
import { badgeClass, type Tone } from './classes'

withDefaults(defineProps<{ tone?: Tone }>(), { tone: 'neutral' })
</script>

<template>
  <span :class="badgeClass(tone)"><slot /></span>
</template>
