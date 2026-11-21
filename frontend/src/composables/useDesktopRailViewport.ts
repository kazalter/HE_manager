import { onBeforeUnmount, onMounted, ref } from 'vue'

export function useDesktopRailViewport() {
  const isWideDesktop = ref(typeof window !== 'undefined' ? window.innerWidth >= 1024 : true)
  const update = () => {
    isWideDesktop.value = window.innerWidth >= 1024
  }
  onMounted(() => window.addEventListener('resize', update, { passive: true }))
  onBeforeUnmount(() => window.removeEventListener('resize', update))
  return isWideDesktop
}
