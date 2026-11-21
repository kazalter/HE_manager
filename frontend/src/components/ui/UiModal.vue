<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
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
  layer?: 'default' | 'viewer'
}>(), {
  description: '',
  size: 'md',
  placement: 'center',
  closeOnBackdrop: true,
  hideClose: false,
  layer: 'default',
})

const emit = defineEmits<{ close: [] }>()
const id = useId()
const dialogRef = ref<HTMLDialogElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const usesNativeModal = ref(false)
let restoreFocus: HTMLElement | null = null
let pressedOutside = false

const supportsClosedBy = typeof HTMLDialogElement !== 'undefined' && 'closedBy' in HTMLDialogElement.prototype

const close = () => {
  if (!open.value) return
  open.value = false
  emit('close')
}

const syncDialogState = async (value: boolean) => {
  await nextTick()
  const dialog = dialogRef.value
  if (!dialog) return

  if (value) {
    restoreFocus = document.activeElement as HTMLElement | null
    if (typeof dialog.showModal === 'function') {
      try {
        if (!dialog.open) dialog.showModal()
        usesNativeModal.value = true
      } catch {
        dialog.setAttribute('open', '')
        usesNativeModal.value = false
      }
    } else {
      dialog.setAttribute('open', '')
      usesNativeModal.value = false
    }
    await nextTick()
    const autofocusTarget = panelRef.value?.querySelector<HTMLElement>('[autofocus]')
    if (autofocusTarget) autofocusTarget.focus()
  } else {
    if (typeof dialog.close === 'function' && dialog.open) {
      try {
        dialog.close()
      } catch {
        dialog.removeAttribute('open')
      }
    } else {
      dialog.removeAttribute('open')
    }
    if (!usesNativeModal.value) {
      restoreFocus?.focus?.()
    }
    restoreFocus = null
  }
}

watch(open, value => {
  void syncDialogState(value)
}, { immediate: true })

onMounted(() => {
  if (open.value) void syncDialogState(true)
})

onBeforeUnmount(() => {
  const dialog = dialogRef.value
  if (dialog?.open && typeof dialog.close === 'function') {
    try { dialog.close() } catch { dialog.removeAttribute('open') }
  }
})

const onCancel = (event: Event) => {
  if (!props.closeOnBackdrop && props.hideClose) {
    event.preventDefault()
    return
  }
  event.preventDefault()
  close()
}

const onNativeClose = () => {
  if (open.value) {
    open.value = false
    emit('close')
  }
}

const isOutsidePanel = (event: PointerEvent) => {
  const rect = panelRef.value?.getBoundingClientRect()
  if (!rect) return false
  return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom
}

const onPointerDown = (event: PointerEvent) => {
  if (!props.closeOnBackdrop) {
    pressedOutside = false
    return
  }
  if (!supportsClosedBy || !usesNativeModal.value) {
    pressedOutside = isOutsidePanel(event)
  }
}

const onPointerUp = (event: PointerEvent) => {
  if (!props.closeOnBackdrop) return
  if ((!supportsClosedBy || !usesNativeModal.value) && pressedOutside && isOutsidePanel(event)) {
    close()
  }
  pressedOutside = false
}

const onFallbackClick = (event: MouseEvent) => {
  if (!props.closeOnBackdrop) return
  if (event.target === dialogRef.value) close()
}

const onFallbackKeydown = (event: KeyboardEvent) => {
  if ((!usesNativeModal.value || !event.isTrusted) && event.key === 'Escape') {
    event.stopPropagation()
    close()
  }
}

const widths = { sm: 'sm:max-w-[400px]', md: 'sm:max-w-[560px]', lg: 'sm:max-w-[760px]', xl: 'sm:max-w-[1000px]' }
</script>

<template>
  <Teleport to="body">
    <dialog
      v-if="open"
      ref="dialogRef"
      :closedby="closeOnBackdrop ? 'any' : 'closerequest'"
      :role="usesNativeModal ? undefined : 'dialog'"
      :aria-modal="usesNativeModal ? undefined : 'true'"
      :aria-labelledby="`${id}-title`"
      :aria-describedby="description ? `${id}-desc` : undefined"
      class="ui-modal ui-modal-dialog m-0 max-h-none max-w-none border-0 bg-transparent p-0 text-ink is-open"
      :class="placement === 'right' ? 'ui-modal-dialog--right' : 'ui-modal-dialog--center'"
      :style="{ zIndex: layer === 'viewer' ? 300 : 200 }"
      @cancel="onCancel"
      @close="onNativeClose"
      @pointerdown="onPointerDown"
      @pointerup="onPointerUp"
      @click="onFallbackClick"
      @keydown="onFallbackKeydown"
    >
      <div
        v-if="open"
        class="ui-modal-backdrop-grid flex h-full w-full"
        :class="props.placement === 'right' ? 'justify-end' : 'items-end justify-center sm:items-center sm:p-6'"
        @click.self="closeOnBackdrop && close()"
      >
        <section
          ref="panelRef"
          tabindex="-1"
          class="ui-modal-panel squircle flex w-full flex-col border-line-strong glass-elevated text-ink shadow-modal focus:outline-none"
          :class="props.placement === 'right'
            ? 'h-full max-w-[min(440px,100vw)] border-l'
            : ['max-h-[calc(var(--he-app-height,100vh)-24px)] rounded-t-3xl border-t sm:max-h-[calc(var(--he-app-height,100vh)-48px)] sm:rounded-3xl sm:border', widths[size]]"
        >
          <header class="flex shrink-0 items-start gap-3 border-b border-line/70 px-5 pt-5 pb-3.5 sm:px-6">
            <div class="min-w-0 flex-1">
              <h2 :id="`${id}-title`" class="text-heading font-semibold text-ink">{{ title }}</h2>
              <p v-if="description" :id="`${id}-desc`" class="mt-1 text-meta text-subtle">{{ description }}</p>
            </div>
            <UiIconButton v-if="!hideClose" label="关闭" size="sm" class="-mr-1.5 -mt-1" @click="close">
              <X :size="18" aria-hidden="true" />
            </UiIconButton>
          </header>
          <div class="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-4 sm:px-6">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="ui-modal-footer flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-line/70 px-5 py-4 sm:px-6">
            <slot name="footer" />
          </footer>
        </section>
      </div>
    </dialog>
  </Teleport>
</template>

<style>
html.he-keyboard-open .ui-modal-dialog {
  height: var(--he-app-height);
}

.ui-modal-dialog {
  display: none;
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
}

.ui-modal-dialog[open],
.ui-modal-dialog.is-open {
  display: block;
}

.ui-modal-dialog:not(:modal).is-open {
  background: rgb(0 0 0 / 0.6);
}

.ui-modal-dialog::backdrop {
  background: rgb(0 0 0 / 0);
  backdrop-filter: blur(0px);
  transition-property: background-color, backdrop-filter, display, overlay;
  transition-duration: 180ms;
  transition-timing-function: var(--ease-out);
  transition-behavior: allow-discrete;
}

.ui-modal-dialog[open]::backdrop {
  background: rgb(0 0 0 / 0.62);
  backdrop-filter: blur(6px);
  @starting-style {
    background: rgb(0 0 0 / 0);
    backdrop-filter: blur(0px);
  }
}

.ui-modal-panel {
  padding-bottom: var(--he-safe-bottom, env(safe-area-inset-bottom, 0px));
  box-shadow: var(--he-shadow-modal), inset 0 1px 0 var(--he-border-specular);
}

@media (prefers-reduced-motion: no-preference) {
  .ui-modal-dialog[open] .ui-modal-panel {
    opacity: 1;
    translate: 0 0;
    scale: 1;
    transition: opacity 180ms var(--ease-out), translate 220ms var(--ease-out), scale 220ms var(--ease-out);
    @starting-style {
      opacity: 0;
      translate: 0 14px;
      scale: 0.985;
    }
  }

  .ui-modal-dialog--right[open] .ui-modal-panel {
    @starting-style {
      opacity: 0;
      translate: 24px 0;
      scale: 1;
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .ui-modal-dialog::backdrop {
    transition-duration: 80ms;
  }
  .ui-modal-dialog[open] .ui-modal-panel {
    transition: opacity 80ms linear;
  }
}
</style>
