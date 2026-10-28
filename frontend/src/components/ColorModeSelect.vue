<script setup lang="ts">
import { Monitor, Moon, Sun } from 'lucide-vue-next'
import { animateColorMode, themeState, type ColorMode } from '../theme'
const modes = [
  { id: 'light' as ColorMode, label: '白天', icon: Sun },
  { id: 'dark' as ColorMode, label: '黑夜', icon: Moon },
  { id: 'system' as ColorMode, label: '跟随系统', icon: Monitor },
]
</script>

<template>
  <div role="group" aria-label="外观模式" class="grid grid-cols-3 gap-1 rounded-xl border border-line bg-surface-2 p-1">
    <button v-for="mode in modes" :key="mode.id" type="button" :aria-pressed="themeState.mode === mode.id" class="flex min-h-11 items-center justify-center gap-2 rounded-lg px-2 text-meta font-medium transition-colors focus-ring-inset" :class="themeState.mode === mode.id ? 'bg-surface text-accent shadow-sm' : 'text-muted hover:bg-surface-3 hover:text-ink'" @click="animateColorMode(mode.id, $event)">
      <component :is="mode.icon" :size="17" aria-hidden="true" />{{ mode.label }}
    </button>
  </div>
</template>
