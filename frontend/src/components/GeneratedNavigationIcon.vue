<script setup lang="ts">
import { computed } from 'vue'
import { themeState } from '../theme'

const props = defineProps<{ name: 'home' | 'video' | 'manga' | 'image' | 'audio' | 'favorite' | 'sun' | 'moon' | 'logout' }>()
const positions = {
  home: [184, 186], video: [444, 186], manga: [704, 186],
  image: [184, 444], audio: [444, 444], favorite: [704, 444],
  sun: [184, 703], moon: [444, 703], logout: [704, 703],
} as const
const position = computed(() => ({
  '--icon-x': positions[props.name][0] + (themeState.resolvedMode === 'dark' ? 887 : 0),
  '--icon-y': positions[props.name][1],
}))
</script>

<template><span class="he-generated-nav-icon" :style="position" aria-hidden="true"></span></template>

<style scoped>
.he-generated-nav-icon {
  display: block;
  flex: none;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  filter: grayscale(1);
  background: url('../assets/navigation-icons-generated.png') no-repeat;
  background-size: 177.4px 88.7px;
  background-position: calc(12px - var(--icon-x) * 0.1px) calc(12px - var(--icon-y) * 0.1px);
}
</style>
