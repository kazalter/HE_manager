<script setup lang="ts">
import { onActivated, onDeactivated, ref, watch } from 'vue'
import { SlidersHorizontal } from 'lucide-vue-next'
import { UiButton, UiModal, badgeClass, type Tone } from '../ui'

// Keep the collection full width. Configuration is an on-demand drawer, while
// its status and entry point remain available throughout a long collection.
const props = withDefaults(defineProps<{
  /** Source name shown in the persistent collection toolbar. */
  sourceName?: string
  /** Settings action and drawer title, e.g. "同步设置". */
  title?: string
  /** Short status chip, e.g. "已同步". */
  status?: string
  statusTone?: Tone
  /** One line under the title, e.g. the last sync time. */
  meta?: string
  /** Open setup once data shows nothing is configured yet. */
  defaultOpen?: boolean
}>(), {
  sourceName: '',
  title: '同步设置',
  status: '',
  statusTone: 'neutral',
  meta: '',
  defaultOpen: false,
})

const open = ref(props.defaultOpen)
const emit = defineEmits<{ settingsClosed: [] }>()
defineExpose({ openSettings: () => { open.value = true }, closeSettings: () => { open.value = false } })
let active = true
watch(() => props.defaultOpen, value => { if (value && active) open.value = true })
onActivated(() => { active = true })
onDeactivated(() => { active = false; open.value = false })
</script>

<template>
  <section class="min-w-0 space-y-4">
    <header class="sticky top-0 z-20 -mt-3 bg-background/95 py-3 backdrop-blur-sm" :aria-label="`${sourceName || title} 状态与设置`">
      <div class="flex items-center gap-3 rounded-xl border border-line bg-surface px-3 py-3 sm:gap-4 sm:px-4">
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h2 class="text-body font-semibold text-ink">{{ sourceName || title }}</h2>
            <span v-if="status" :class="badgeClass(statusTone)">{{ status }}</span>
          </div>
          <p v-if="meta" class="mt-0.5 truncate text-meta text-subtle tabular-nums">{{ meta }}</p>
        </div>
        <UiButton class="shrink-0" size="sm" aria-haspopup="dialog" :aria-expanded="open" @click="open = true">
          <template #icon><SlidersHorizontal :size="16" aria-hidden="true" /></template>
          {{ title }}
        </UiButton>
      </div>
    </header>

    <div class="min-w-0 space-y-4">
      <slot />
    </div>

    <UiModal v-model:open="open" :title="title" :description="sourceName" placement="right" @close="emit('settingsClosed')">
      <div class="space-y-5 pt-2">
        <slot name="config" />
      </div>
    </UiModal>
  </section>
</template>
