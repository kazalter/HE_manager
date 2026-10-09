<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { X } from 'lucide-vue-next'
import UiIconButton from './UiIconButton.vue'

const open = defineModel<boolean>('open', { required: true })
const props = withDefaults(defineProps<{
  title: string
  description?: string
  /** Panel width: sm 400 · md 560 · lg 760 · xl 1000 px. */
  size?: 'sm' | 'md' | 'lg' | 'xl'
  /** center = dialog (bottom sheet on phones), right = side drawer. */
  placement?: 'center' | 'right'
  closeOnBackdrop?: boolean
  hideClose?: boolean
}>(), {
  description: '',
  size: 'md',
  placement: 'center',
  closeOnBackdrop: true,
  hideClose: false,
})

const emit = defineEmits<{ close: [] }>()
const id = useId()
const panelRef = ref<HTMLElement | null>(null)
let restoreFocus: HTMLElement | null = null

const close = () => {
  open.value = false
  emit('close')
}

const focusables = () => Array.from(panelRef.value?.querySelectorAll<HTMLElement>(
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
) || []).filter(element => element.getClientRects().length)

const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    event.stopPropagation()
    close()
    return
  }
  if (event.key !== 'Tab') return
  const items = focusables()
  const first = items[0], last = items[items.length - 1]
  if (!first || !last) { event.preventDefault(); return }
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}

watch(open, async value => {
  if (value) {
    restoreFocus = document.activeElement as HTMLElement | null
    await nextTick()
    const target = panelRef.value?.querySelector<HTMLElement>('[autofocus]') || focusables()[0] || panelRef.value
    target?.focus()
  } else {
    restoreFocus?.focus?.()
    restoreFocus = null
  }
}, { immediate: true })

onBeforeUnmount(() => { if (open.value) restoreFocus?.focus?.() })

const widths = { sm: 'sm:max-w-[400px]', md: 'sm:max-w-[560px]', lg: 'sm:max-w-[760px]', xl: 'sm:max-w-[1000px]' }
</script>

<template>
  <Teleport to="body">
    <Transition name="ui-modal">
      <div
        v-if="open"
        class="ui-modal fixed inset-0 z-[200] flex bg-black/60"
        :class="props.placement === 'right' ? 'justify-end' : 'items-end justify-center sm:items-center sm:p-6'"
        @click.self="closeOnBackdrop && close()"
        @keydown="onKeydown"
      >
        <section
          ref="panelRef"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="`${id}-title`"
          :aria-describedby="description ? `${id}-desc` : undefined"
          tabindex="-1"
          class="ui-modal-panel flex w-full flex-col border-line-strong bg-surface-3 text-ink shadow-modal focus:outline-none"
          :class="props.placement === 'right'
            ? 'h-full max-w-[min(440px,100vw)] border-l'
            : ['max-h-[calc(var(--he-app-height,100vh)-24px)] rounded-t-3xl border-t sm:max-h-[calc(var(--he-app-height,100vh)-48px)] sm:rounded-3xl sm:border', widths[size]]"
        >
          <header class="flex shrink-0 items-start gap-3 px-5 pt-5 pb-3 sm:px-6">
            <div class="min-w-0 flex-1">
              <h2 :id="`${id}-title`" class="text-heading font-semibold text-ink">{{ title }}</h2>
              <p v-if="description" :id="`${id}-desc`" class="mt-1 text-meta text-subtle">{{ description }}</p>
            </div>
            <UiIconButton v-if="!hideClose" label="关闭" size="sm" class="-mr-1.5 -mt-1" @click="close"><X :size="18" aria-hidden="true" /></UiIconButton>
          </header>
          <div class="min-h-0 flex-1 overflow-y-auto px-5 pb-5 sm:px-6">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="ui-modal-footer flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-line px-5 py-4 sm:px-6">
            <slot name="footer" />
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style>
.ui-modal-panel { padding-bottom: env(safe-area-inset-bottom); }
.ui-modal-enter-active, .ui-modal-leave-active { transition: opacity var(--duration-base) var(--ease-out); }
.ui-modal-enter-active .ui-modal-panel, .ui-modal-leave-active .ui-modal-panel { transition: transform var(--duration-slow) var(--ease-out); }
.ui-modal-enter-from, .ui-modal-leave-to { opacity: 0; }
.ui-modal-enter-from .ui-modal-panel, .ui-modal-leave-to .ui-modal-panel { transform: translateY(16px); }
.ui-modal-enter-from.justify-end .ui-modal-panel, .ui-modal-leave-to.justify-end .ui-modal-panel { transform: translateX(24px); }
@media (min-width: 640px) {
  .ui-modal-enter-from:not(.justify-end) .ui-modal-panel, .ui-modal-leave-to:not(.justify-end) .ui-modal-panel { transform: translateY(8px) scale(0.98); }
}
</style>
