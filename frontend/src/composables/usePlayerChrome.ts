import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

/** One idle timer; paused playback and active controls stay visible. */
export function usePlayerChrome(held: Ref<boolean>) {
  const visible = ref(true)
  let timer: ReturnType<typeof setTimeout> | undefined
  function reveal() {
    clearTimeout(timer)
    visible.value = true
    if (!held.value) timer = setTimeout(() => { visible.value = false }, 2500)
  }
  watch(held, reveal, { immediate: true })
  onBeforeUnmount(() => clearTimeout(timer))
  return { visible, reveal }
}
