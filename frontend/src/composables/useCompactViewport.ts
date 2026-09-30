import { onMounted, onBeforeUnmount, ref } from 'vue'

export function useCompactViewport() {
  const compact = ref(window.innerWidth < 900)
  const update = () => { compact.value = window.innerWidth < 900 }
  onMounted(() => window.addEventListener('resize', update, { passive: true }))
  onBeforeUnmount(() => window.removeEventListener('resize', update))
  return compact
}
