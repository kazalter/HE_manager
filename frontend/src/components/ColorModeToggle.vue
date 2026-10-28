<script setup lang="ts">
import { Moon, Sun } from 'lucide-vue-next'
import { themeState, toggleColorMode } from '../theme'
import GeneratedNavigationIcon from './GeneratedNavigationIcon.vue'
withDefaults(defineProps<{ compact?: boolean; showTooltip?: boolean; generatedIcon?: boolean }>(), { compact: false, showTooltip: true, generatedIcon: false })
</script>

<template>
  <button type="button" :aria-label="themeState.resolvedMode === 'dark' ? '切换到白天模式' : '切换到黑夜模式'" :title="themeState.resolvedMode === 'dark' ? '切换到白天模式' : '切换到黑夜模式'" class="group relative flex min-h-10 items-center rounded-lg text-body font-medium text-muted transition-colors hover:bg-surface-2 hover:text-ink focus-ring" :class="compact ? 'size-10 justify-center' : 'w-full gap-3 px-3'" @click="toggleColorMode">
    <GeneratedNavigationIcon v-if="generatedIcon" :name="themeState.resolvedMode === 'dark' ? 'sun' : 'moon'" />
    <Sun v-else-if="themeState.resolvedMode === 'dark'" :size="18" class="shrink-0" aria-hidden="true" />
    <Moon v-else :size="18" class="shrink-0" aria-hidden="true" />
    <span v-if="!compact">{{ themeState.resolvedMode === 'dark' ? '白天模式' : '黑夜模式' }}</span>
    <span v-else-if="showTooltip" class="he-rail-tip">{{ themeState.resolvedMode === 'dark' ? '白天模式' : '黑夜模式' }}</span>
  </button>
</template>
