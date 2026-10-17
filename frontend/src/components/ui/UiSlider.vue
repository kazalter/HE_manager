<script setup lang="ts">
import { useId } from 'vue'
const model = defineModel<number>({ required: true })
withDefaults(defineProps<{ label: string; min?: number; max?: number; step?: number; disabled?: boolean; valueText?: string; hideLabel?: boolean }>(), {
  min: 0, max: 100, step: 1, disabled: false, hideLabel: false,
})
const emit = defineEmits<{ commit: [value: number] }>()
const id = useId()
</script>
<template>
  <div class="min-w-0">
    <label :for="id" :class="hideLabel ? 'sr-only' : 'mb-2 block text-meta text-muted'">{{ label }}</label>
    <input :id="id" v-model.number="model" type="range" :min="min" :max="max" :step="step" :disabled="disabled" :aria-valuetext="valueText" class="he-slider block h-8 w-full cursor-pointer accent-accent focus-ring disabled:cursor-default disabled:opacity-40" @change="emit('commit', Number(($event.target as HTMLInputElement).value))" />
  </div>
</template>
