<script setup lang="ts">
import { computed, type Component } from 'vue'
import UiSpinner from './UiSpinner.vue'
import { buttonClass, type ButtonVariant, type ControlSize } from './classes'

const props = withDefaults(defineProps<{
  variant?: ButtonVariant
  size?: ControlSize
  /** Render as another element or component, e.g. `'a'` or `RouterLink`. */
  as?: string | Component
  type?: 'button' | 'submit' | 'reset'
  disabled?: boolean
  loading?: boolean
  block?: boolean
}>(), {
  variant: 'secondary',
  size: 'md',
  as: 'button',
  type: 'button',
  disabled: false,
  loading: false,
  block: false,
})

const isButton = computed(() => props.as === 'button')
</script>

<template>
  <component
    :is="as"
    :type="isButton ? type : undefined"
    :disabled="isButton ? disabled || loading : undefined"
    :aria-disabled="!isButton && (disabled || loading) ? 'true' : undefined"
    :aria-busy="loading ? 'true' : undefined"
    :class="buttonClass(variant, size, block)"
  >
    <UiSpinner v-if="loading" :size="size === 'sm' ? 14 : 16" />
    <slot v-else name="icon" />
    <slot />
    <slot name="trailing" />
  </component>
</template>
