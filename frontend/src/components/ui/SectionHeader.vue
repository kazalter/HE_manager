<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  description?: string
  count?: number | string
  as?: 'h2' | 'h3'
}>(), {
  description: '',
  count: undefined,
  as: 'h2',
})
</script>

<template>
  <div class="mb-3 flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
    <div class="flex min-w-0 items-center gap-2.5">
      <slot name="leading" />
      <div class="min-w-0">
        <div class="flex items-baseline gap-2">
          <component :is="as" class="truncate text-heading font-semibold text-ink">{{ title }}</component>
          <span v-if="count !== undefined" class="shrink-0 text-meta text-subtle tabular-nums">{{ count }}</span>
        </div>
        <p v-if="description || $slots.description" class="mt-0.5 text-meta text-subtle">
          <slot name="description">{{ description }}</slot>
        </p>
      </div>
    </div>
    <div v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>
