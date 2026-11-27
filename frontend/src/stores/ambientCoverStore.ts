import { reactive } from 'vue'

interface AmbientCoverState {
  coverUrl: string
}

const state = reactive<AmbientCoverState>({
  coverUrl: '',
})

export const ambientCoverStore = {
  state,
  setCover(url: string | null | undefined) {
    state.coverUrl = url?.trim() || ''
  },
  clearCover() {
    state.coverUrl = ''
  },
}
