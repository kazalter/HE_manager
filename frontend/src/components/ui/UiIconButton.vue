<script setup lang="ts">
import { computed, type Component } from 'vue'
import { iconButtonClass, type ButtonVariant, type ControlSize } from './classes'

const props = withDefaults(defineProps<{
  /** Accessible name; also shown as the native tooltip. */
  label: string
  variant?: ButtonVariant
  size?: ControlSize
  as?: string | Component
  type?: 'button' | 'submit' | 'reset'
  disabled?: boolean
  /** Toggle state. Leave undefined for a plain action button. */
  pressed?: boolean
  /** Set false when a visible tooltip already exists. */
  tooltip?: boolean
}>(), {
  variant: 'ghost',
  size: 'md',
  as: 'button',
  type: 'button',
  disabled: false,
  pressed: undefined,
  tooltip: true,
})

const isButton = computed(() => props.as === 'button')
</script>

<template>
  <component
    :is="as"
    :type="isButton ? type : undefined"
    :disabled="isButton ? disabled : undefined"
    :aria-disabled="!isButton && disabled ? 'true' : undefined"
    :aria-label="label"
    :title="tooltip ? label : undefined"
    :aria-pressed="pressed === undefined ? undefined : String(pressed)"
    :class="iconButtonClass(variant, size)"
  >
    <slot />
  </component>
</template>
