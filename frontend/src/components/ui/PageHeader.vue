<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  description?: string
  /** Item count shown next to the title, e.g. `44` or `'44 项'`. */
  count?: number | string
  /** Stick to the top of the scroll area with a solid background. */
  sticky?: boolean
  as?: 'h1' | 'h2'
}>(), {
  description: '',
  count: undefined,
  sticky: false,
  as: 'h1',
})
</script>

<template>
  <header
    class="he-page-header page-gutter"
    :class="sticky ? 'he-sticky-retract sticky top-0 z-30 border-b border-line glass-surface py-3 lg:py-3.5 transition-transform duration-200' : 'pt-5 pb-4 lg:pt-7 lg:pb-5'"
  >
    <div class="page-container">
      <div class="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div class="flex min-w-0 items-center gap-3">
          <slot name="leading" />
          <div class="min-w-0">
            <div class="flex min-w-0 flex-wrap items-center gap-2.5">
              <component :is="as" class="text-title font-semibold tracking-tight text-ink">{{ title }}</component>
              <span v-if="count !== undefined" class="inline-flex shrink-0 items-center rounded-full border border-line bg-surface-2 px-2.5 py-0.5 text-caption font-medium text-muted tabular-nums">{{ count }}</span>
            </div>
            <p v-if="description || $slots.description" class="mt-1 text-meta text-subtle">
              <slot name="description">{{ description }}</slot>
            </p>
          </div>
        </div>
        <div v-if="$slots.actions" class="flex shrink-0 flex-wrap items-center gap-2">
          <slot name="actions" />
        </div>
      </div>
      <div v-if="$slots.default" class="mt-4">
        <slot />
      </div>
    </div>
  </header>
</template>
