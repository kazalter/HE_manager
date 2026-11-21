<script setup lang="ts">
import { Moon, Sun } from 'lucide-vue-next'
import { themeState, toggleColorMode } from '../theme'
withDefaults(defineProps<{ compact?: boolean; showTooltip?: boolean; generatedIcon?: boolean }>(), {
  compact: false,
  showTooltip: true,
  generatedIcon: false,
})
</script>

<template>
  <button
    type="button"
    :aria-label="themeState.resolvedMode === 'dark' ? '切换到白天模式' : '切换到黑夜模式'"
    :title="themeState.resolvedMode === 'dark' ? '切换到白天模式' : '切换到黑夜模式'"
    class="group relative flex min-h-9 items-center rounded-xl text-body font-medium text-muted transition-colors duration-150 hover:bg-surface-2 hover:text-ink focus-ring"
    :class="compact ? 'size-9 justify-center' : 'w-full gap-3 px-3 py-2'"
    @click="toggleColorMode"
  >
    <Sun v-if="themeState.resolvedMode === 'dark'" :size="17" class="shrink-0 text-amber-300/90 transition-transform duration-200 group-hover:rotate-12" aria-hidden="true" />
    <Moon v-else :size="17" class="shrink-0 text-accent transition-transform duration-200 group-hover:-rotate-12" aria-hidden="true" />
    <span v-if="!compact">{{ themeState.resolvedMode === 'dark' ? '白天模式' : '黑夜模式' }}</span>
    <span v-else-if="showTooltip" class="he-rail-tip">{{ themeState.resolvedMode === 'dark' ? '白天模式' : '黑夜模式' }}</span>
  </button>
</template>
