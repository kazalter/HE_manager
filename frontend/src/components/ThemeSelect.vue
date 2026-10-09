<script setup lang="ts" generic="T extends string | number">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Check, ChevronDown } from 'lucide-vue-next'

interface Option { value: T; label: string }

const props = defineProps<{ modelValue: T; options: Option[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: T): void }>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)
// Which row the keyboard cursor sits on while the menu is open.
const activeIndex = ref(0)

const selected = computed(() => props.options.find(o => o.value === props.modelValue) || props.options[0] || null)

function close() {
  open.value = false
}

function toggle() {
  open.value = !open.value
  if (open.value) {
    activeIndex.value = Math.max(0, props.options.findIndex(o => o.value === props.modelValue))
  }
}

function pick(value: T) {
  emit('update:modelValue', value)
  close()
}

function onKeydown(e: KeyboardEvent) {
  if (!open.value) {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
      e.preventDefault()
      toggle()
    }
    return
  }
  if (e.key === 'Escape') {
    close()
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value + 1) % props.options.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value - 1 + props.options.length) % props.options.length
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const opt = props.options[activeIndex.value]
    if (opt) pick(opt.value)
  }
}

// Click-anywhere-else dismisses, matching native select behaviour.
function onDocPointer(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) close()
}

watch(open, isOpen => {
  if (isOpen) document.addEventListener('mousedown', onDocPointer)
  else document.removeEventListener('mousedown', onDocPointer)
})

onBeforeUnmount(() => document.removeEventListener('mousedown', onDocPointer))
</script>

<template>
  <div ref="root" class="relative" @keydown="onKeydown">
    <button
      type="button"
      aria-haspopup="listbox"
      :aria-expanded="open"
      @click="toggle"
      :class="[
        'w-full h-10 flex items-center justify-between gap-2 rounded-lg border bg-surface-2 px-3 text-body text-ink text-left transition-colors duration-150 ease-out focus:outline-none',
        open ? 'border-accent ring-2 ring-accent/25' : 'border-line hover:border-line-strong focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/25',
      ]"
    >
      <span class="truncate">{{ selected?.label }}</span>
      <ChevronDown :size="16" class="shrink-0 text-subtle transition-transform duration-200" :class="open ? 'rotate-180' : ''" aria-hidden="true" />
    </button>

    <transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-1"
    >
      <div
        v-if="open"
        role="listbox"
        class="absolute left-0 right-0 mt-1.5 z-50 max-h-72 overflow-y-auto p-1.5 rounded-2xl border border-line-strong bg-surface-3 shadow-pop"
      >
        <button
          v-for="(opt, i) in options"
          :key="opt.value"
          type="button"
          role="option"
          :aria-selected="opt.value === modelValue"
          @click="pick(opt.value)"
          @mousemove="activeIndex = i"
          :class="[
            'w-full h-9 flex items-center justify-between gap-2 px-2.5 rounded-lg text-body text-left transition-colors duration-100',
            opt.value === modelValue ? 'text-ink font-medium' : 'text-muted',
            activeIndex === i ? 'bg-line-strong/60 text-ink' : '',
          ]"
        >
          <span class="truncate">{{ opt.label }}</span>
          <Check v-if="opt.value === modelValue" :size="15" class="shrink-0 text-accent" aria-hidden="true" />
        </button>
      </div>
    </transition>
  </div>
</template>
