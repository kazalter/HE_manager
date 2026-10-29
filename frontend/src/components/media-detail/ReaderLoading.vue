<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Loader2 } from 'lucide-vue-next'

const props = defineProps<{ active: boolean; label: string }>()
const visible = ref(false)
let timer: number | undefined
watch(() => [props.active, props.label] as const, () => {
  window.clearTimeout(timer)
  visible.value = false
  if (props.active) timer = window.setTimeout(() => { visible.value = true }, 300)
}, { immediate: true })
onBeforeUnmount(() => window.clearTimeout(timer))
</script>

<template>
  <div v-if="visible" role="status" aria-live="polite" class="pointer-events-none flex flex-col items-center justify-center gap-3 px-4 text-center text-meta text-white/75">
    <Loader2 :size="28" class="animate-spin motion-reduce:animate-none" aria-hidden="true" />
    <span>{{ label }}</span>
  </div>
</template>
