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
    :class="sticky ? 'sticky top-0 z-30 border-b border-line bg-background/95 py-3 lg:py-4' : 'pt-6 pb-5 lg:pt-8 lg:pb-6'"
  >
    <div class="page-container">
      <div class="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div class="flex min-w-0 items-center gap-3">
          <slot name="leading" />
          <div class="min-w-0">
            <div class="flex min-w-0 items-baseline gap-2.5">
              <component :is="as" class="truncate text-title font-semibold text-ink">{{ title }}</component>
              <span v-if="count !== undefined" class="shrink-0 text-meta text-subtle tabular-nums">{{ count }}</span>
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
