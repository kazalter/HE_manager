import { onMounted, onUnmounted } from 'vue'

/** Registers capture-phase media shortcuts and guarantees symmetric cleanup. */
export function useMediaKeyboard(
  onKeydown: (event: KeyboardEvent) => void,
  onKeyup: (event: KeyboardEvent) => void,
  onBlur: () => void,
) {
  onMounted(() => {
    window.addEventListener('keydown', onKeydown, { capture: true })
    window.addEventListener('keyup', onKeyup, { capture: true })
    window.addEventListener('blur', onBlur)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', onKeydown, { capture: true })
    window.removeEventListener('keyup', onKeyup, { capture: true })
    window.removeEventListener('blur', onBlur)
  })
}
