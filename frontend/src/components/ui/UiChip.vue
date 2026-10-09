<script setup lang="ts">
import { computed } from 'vue'
import { X } from 'lucide-vue-next'
import { chipClass } from './classes'

const props = withDefaults(defineProps<{
  /** Toggle state for filter chips. Undefined renders a plain chip. */
  selected?: boolean
  size?: 'sm' | 'md'
  as?: 'button' | 'span'
  count?: number | string
  /** Shows a remove button that emits `remove`. */
  removable?: boolean
  removeLabel?: string
}>(), {
  selected: undefined,
  size: 'md',
  as: 'button',
  count: undefined,
  removable: false,
  removeLabel: '移除',
})

const emit = defineEmits<{ remove: [] }>()
// A removable chip holds its own remove button, so its root cannot be a button.
const root = computed(() => props.removable ? 'span' : props.as)
const isButton = computed(() => root.value === 'button')
</script>

<template>
  <component
    :is="root"
    :type="isButton ? 'button' : undefined"
    :aria-pressed="isButton && selected !== undefined ? String(selected) : undefined"
    :class="[chipClass(!!selected, size), removable ? 'pr-1' : '']"
  >
    <slot name="leading" />
    <span class="truncate"><slot /></span>
    <span v-if="count !== undefined" class="tabular-nums" :class="selected ? 'text-accent-glow/75' : 'text-subtle'">{{ count }}</span>
    <button
      v-if="removable"
      type="button"
      class="grid size-5 place-items-center rounded-full text-subtle transition-colors hover:bg-surface-3 hover:text-ink focus-ring"
      :aria-label="removeLabel"
      @click.stop="emit('remove')"
    >
      <X :size="12" aria-hidden="true" />
    </button>
  </component>
</template>
