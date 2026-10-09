<script setup lang="ts">
import { computed, ref, useAttrs, useSlots } from 'vue'
import { controlClass, type ControlSize } from './classes'

defineOptions({ inheritAttrs: false })

const model = defineModel<string | number>()
const props = withDefaults(defineProps<{
  type?: string
  size?: ControlSize
  invalid?: boolean
}>(), {
  type: 'text',
  size: 'md',
  invalid: false,
})

// `class`/`style` style the wrapper; every other attribute (placeholder,
// aria-label, autocomplete, @keydown …) goes to the <input>.
const attrs = useAttrs()
const slots = useSlots()
const wrapperAttrs = computed(() => ({ class: attrs.class, style: attrs.style }))
const inputAttrs = computed(() => {
  const { class: _class, style: _style, ...rest } = attrs
  return rest
})
const inputRef = ref<HTMLInputElement | null>(null)
defineExpose({ focus: () => inputRef.value?.focus(), select: () => inputRef.value?.select(), el: inputRef })
</script>

<template>
  <div class="relative flex min-w-0 items-center" v-bind="wrapperAttrs">
    <span v-if="slots.leading" class="pointer-events-none absolute left-3 flex text-subtle" aria-hidden="true">
      <slot name="leading" />
    </span>
    <input
      ref="inputRef"
      v-model="model"
      v-bind="inputAttrs"
      :type="props.type"
      :aria-invalid="invalid ? 'true' : undefined"
      :class="[controlClass(size, invalid), slots.leading ? 'pl-9' : '', slots.trailing ? 'pr-10' : '']"
    />
    <span v-if="slots.trailing" class="absolute right-1.5 flex items-center">
      <slot name="trailing" />
    </span>
  </div>
</template>
