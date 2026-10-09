<script setup lang="ts">
import { ref, useId, watch } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import { badgeClass, type Tone } from '../ui'

// Shared shell for every external source panel: the list/content is the hero
// on the left, the sync configuration sits in one card on the right (xl+).
// Below xl the card collapses into a one-line summary above the content.
const props = withDefaults(defineProps<{
  /** Card title, e.g. "同步设置". */
  title?: string
  /** Short status chip, e.g. "已同步". */
  status?: string
  statusTone?: Tone
  /** One line under the title, e.g. the last sync time. */
  meta?: string
  /** Expand on narrow screens, e.g. once data shows nothing is set up yet. */
  defaultOpen?: boolean
}>(), {
  title: '同步设置',
  status: '',
  statusTone: 'neutral',
  meta: '',
  defaultOpen: false,
})

const open = ref(props.defaultOpen)
watch(() => props.defaultOpen, value => { if (value) open.value = true })
const bodyId = `source-config-${useId()}`
</script>

<template>
  <section class="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_360px] xl:gap-8">
    <aside class="rounded-2xl border border-line bg-surface xl:order-2" :aria-label="title">
      <button
        type="button"
        class="flex w-full items-center gap-3 rounded-2xl px-4 py-3.5 text-left focus-ring-inset sm:px-5 xl:pointer-events-none xl:pb-0 xl:pt-5"
        :aria-expanded="open"
        :aria-controls="bodyId"
        @click="open = !open"
      >
        <div class="min-w-0 flex-1">
          <div class="flex min-w-0 items-center gap-2">
            <h2 class="truncate text-body font-semibold text-ink">{{ title }}</h2>
            <span v-if="status" :class="badgeClass(statusTone)">{{ status }}</span>
          </div>
          <p v-if="meta" class="mt-0.5 truncate text-meta text-subtle tabular-nums">{{ meta }}</p>
        </div>
        <ChevronDown
          :size="18"
          class="shrink-0 text-subtle transition-transform duration-150 xl:hidden"
          :class="open ? 'rotate-180' : ''"
          aria-hidden="true"
        />
      </button>
      <div :id="bodyId" class="space-y-5 border-t border-line px-4 pb-5 pt-4 sm:px-5 xl:mt-4 xl:block" :class="open ? 'block' : 'hidden'">
        <slot name="config" />
      </div>
    </aside>

    <div class="min-w-0 space-y-4 xl:order-1">
      <slot />
    </div>
  </section>
</template>
