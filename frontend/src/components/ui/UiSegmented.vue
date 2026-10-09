<script setup lang="ts" generic="T extends string | number">
import { ref } from 'vue'
import type { SegmentedOption } from './classes'

const model = defineModel<T>({ required: true })
const props = withDefaults(defineProps<{
  options: SegmentedOption<T>[]
  /** Accessible name of the group, e.g. "排序方式". */
  label: string
  size?: 'sm' | 'md'
  block?: boolean
}>(), {
  size: 'md',
  block: false,
})

const buttons = ref<HTMLButtonElement[]>([])

const onKeydown = (event: KeyboardEvent, index: number) => {
  const step = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 0
  if (!step) return
  event.preventDefault()
  const next = (index + step + props.options.length) % props.options.length
  model.value = props.options[next]!.value
  buttons.value[next]?.focus()
}
</script>

<template>
  <div
    role="radiogroup"
    :aria-label="label"
    class="items-center gap-0.5 rounded-lg border border-line bg-surface p-0.5"
    :class="block ? 'flex w-full' : 'inline-flex'"
  >
    <button
      v-for="(option, index) in options"
      :key="option.value"
      ref="buttons"
      type="button"
      role="radio"
      :aria-checked="model === option.value"
      :aria-label="option.iconOnly ? option.label : undefined"
      :title="option.iconOnly ? option.label : undefined"
      :tabindex="model === option.value ? 0 : -1"
      class="inline-flex min-w-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium transition-colors duration-150 ease-out focus-ring-inset"
      :class="[
        size === 'sm' ? 'h-7 px-2.5 text-caption' : 'h-8 px-3 text-meta',
        block ? 'flex-1' : '',
        model === option.value ? 'bg-surface-3 text-ink shadow-[0_1px_2px_rgb(0_0_0/0.35)]' : 'text-subtle hover:text-ink',
      ]"
      @click="model = option.value"
      @keydown="onKeydown($event, index)"
    >
      <component :is="option.icon" v-if="option.icon" :size="size === 'sm' ? 14 : 15" aria-hidden="true" />
      <span v-if="!option.iconOnly" class="truncate">{{ option.label }}</span>
    </button>
  </div>
</template>
