import { reactive } from 'vue'

const state = reactive({
  open: false,
  activated: false,
  activeRun: false,
  pendingCount: 0,
})

export const assistantPanelStore = {
  state,
  open() {
    state.activated = true
    state.open = true
  },
  close() {
    state.open = false
  },
  toggle() {
    if (state.open) {
      state.open = false
    } else {
      state.activated = true
      state.open = true
    }
  },
  reset() {
    state.open = false
    state.activated = false
    state.activeRun = false
    state.pendingCount = 0
  },
}
