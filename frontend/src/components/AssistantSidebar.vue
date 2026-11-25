<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import AssistantWorkspace from './AssistantWorkspace.vue'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const workspaceRef = ref<InstanceType<typeof AssistantWorkspace> | null>(null)

const onKeydown = (event: KeyboardEvent) => {
  if (!props.open || event.key !== 'Escape') return
  if (workspaceRef.value?.hasSubOverlay?.()) return
  event.stopPropagation()
  emit('close')
}

watch(
  () => props.open,
  active => {
    if (active) document.addEventListener('keydown', onKeydown)
    else document.removeEventListener('keydown', onKeydown)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="he-backdrop">
      <div
        v-show="open"
        class="fixed inset-0 z-[110] bg-black/45 backdrop-blur-[2px]"
        aria-hidden="true"
        @click="emit('close')"
      ></div>
    </Transition>
    <Transition name="he-drawer">
      <aside
        v-show="open"
        id="he-assistant-sidebar"
        role="dialog"
        aria-modal="true"
        aria-label="媒体库管家侧边栏"
        class="fixed inset-y-0 right-0 z-[120] flex w-full max-w-[min(460px,100vw)] flex-col border-l border-line-strong glass-elevated shadow-modal"
        @keydown="onKeydown"
      >
        <AssistantWorkspace ref="workspaceRef" mode="sidebar" @close="emit('close')" />
      </aside>
    </Transition>
  </Teleport>
</template>
