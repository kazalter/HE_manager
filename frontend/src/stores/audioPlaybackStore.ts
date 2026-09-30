import { reactive } from 'vue'
import type { Media } from '../types'
interface AudioControls { togglePlay: () => void; nextTrack: () => void; prevTrack: () => void }
const state = reactive({ media: null as Media | null, expanded: false, playing: false, trackTitle: '', currentTime: 0, duration: 0 })
let controls: AudioControls | null = null
export const audioPlaybackStore = {
  state,
  open(media: Media) {
    if (state.media?.id !== media.id) {
      state.media = { ...media }
      state.playing = false; state.trackTitle = ''; state.currentTime = 0; state.duration = 0
    }
    state.expanded = true
  },
  minimize() { state.expanded = false },
  stop() { state.media = null; state.expanded = false; state.playing = false; controls = null },
  bind(next: AudioControls | null) { controls = next },
  togglePlay() { controls?.togglePlay() },
  nextTrack() { controls?.nextTrack() },
  prevTrack() { controls?.prevTrack() },
}
