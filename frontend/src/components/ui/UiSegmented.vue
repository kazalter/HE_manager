<script setup lang="ts" generic="T extends string | number">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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

const root = ref<HTMLElement | null>(null)
const buttons = ref<HTMLButtonElement[]>([])
const indicatorStyle = ref<{ x: number; w: number; ready: boolean }>({ x: 0, w: 0, ready: false })
let observer: ResizeObserver | undefined

const updateIndicator = async () => {
  await nextTick()
  const idx = props.options.findIndex(opt => opt.value === model.value)
  const target = idx >= 0 ? buttons.value[idx] : undefined
  if (!target || target.offsetWidth <= 0) {
    indicatorStyle.value = { x: 0, w: 0, ready: false }
    return
  }
  indicatorStyle.value = { x: target.offsetLeft, w: target.offsetWidth, ready: true }
}

onMounted(() => {
  void updateIndicator()
  if (root.value && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => { void updateIndicator() })
    observer.observe(root.value)
  }
})

onBeforeUnmount(() => observer?.disconnect())
watch([() => model.value, () => props.options.length], () => { void updateIndicator() })

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
    ref="root"
    role="radiogroup"
    :aria-label="label"
    class="relative items-center gap-0.5 rounded-xl border border-line bg-surface-2/85 p-0.5 shadow-[inset_0_1px_2px_rgb(0_0_0/0.12)]"
    :class="block ? 'flex w-full' : 'inline-flex'"
  >
    <span
      v-if="indicatorStyle.ready"
      aria-hidden="true"
      class="he-seg-pill pointer-events-none absolute top-0.5 bottom-0.5 left-0 rounded-[9px] bg-surface-3 ring-1 ring-inset ring-line-strong/85 shadow-[0_1px_3px_rgb(0_0_0/0.22),inset_0_1px_0_var(--he-border-specular)]"
      :style="{ width: `${indicatorStyle.w}px`, transform: `translateX(${indicatorStyle.x}px)` }"
    ></span>
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
      class="relative z-10 inline-flex min-w-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-[9px] font-medium transition-colors duration-150 ease-out focus-ring-inset active:scale-[0.98]"
      :class="[
        size === 'sm' ? 'min-h-7 px-2.5 py-0.5 text-caption pointer-coarse:min-h-9' : 'min-h-8 px-3 py-1 text-meta pointer-coarse:min-h-10',
        block ? 'flex-1' : '',
        model === option.value
          ? indicatorStyle.ready
            ? 'text-ink'
            : 'bg-surface-3 text-ink ring-1 ring-inset ring-line-strong/80 shadow-[0_1px_3px_rgb(0_0_0/0.25),inset_0_1px_0_var(--he-border-specular)]'
          : 'text-subtle hover:text-ink',
      ]"
      @click="model = option.value"
      @keydown="onKeydown($event, index)"
    >
      <component :is="option.icon" v-if="option.icon" :size="size === 'sm' ? 14 : 15" :class="model === option.value ? 'text-accent-glow' : ''" aria-hidden="true" />
      <span v-if="!option.iconOnly" class="truncate">{{ option.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.he-seg-pill {
  transition: transform 240ms var(--ease-spring), width 240ms var(--ease-spring);
}
@media (prefers-reduced-motion: reduce) {
  .he-seg-pill {
    transition: none;
  }
}
</style>
