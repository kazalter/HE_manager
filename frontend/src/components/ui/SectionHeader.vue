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
  <div class="mb-3.5 flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
    <div class="flex min-w-0 items-center gap-2.5">
      <slot name="leading" />
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <component :is="as" class="text-heading font-semibold tracking-tight text-ink">{{ title }}</component>
          <span v-if="count !== undefined" class="inline-flex shrink-0 items-center rounded-full border border-line bg-surface-2 px-2 py-0.5 text-caption font-medium text-subtle tabular-nums">{{ count }}</span>
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
