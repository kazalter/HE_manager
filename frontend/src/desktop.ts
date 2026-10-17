import { reactive } from 'vue'
import type { DesktopBridge, DesktopConfiguration, VideoEnhancement, ImageEnhancement } from './desktop-contract'
export type { DesktopBridge, DesktopConfiguration, DesktopPlayback, DesktopTrack, DesktopVideoAction, VideoEnhancement, ImageEnhancement } from './desktop-contract'
declare global { interface Window { heDesktop?: DesktopBridge } }
export const desktopBridge = window.heDesktop
export const desktopState = reactive<DesktopConfiguration>({ server: '', videoMode: 'off', imageMode: 'off', platform: '', arch: '', version: '', mpv: false, image: false, videoPresentation: 'embedded' })
export async function initDesktop() {
 if (desktopBridge) {
  document.documentElement.classList.add('he-desktop')
  Object.assign(desktopState, await desktopBridge.configuration())
 }
}
export async function setDesktopPreferences(videoMode: VideoEnhancement, imageMode: ImageEnhancement) {
 if (desktopBridge) Object.assign(desktopState, await desktopBridge.setPreferences({ videoMode, imageMode }))
}
