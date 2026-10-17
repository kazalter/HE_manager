import { reactive } from 'vue'
export type VideoEnhancement = 'off' | 'efficiency' | 'quality'
export type ImageEnhancement = 'off' | 'anime' | 'photo'
export interface DesktopConfiguration { server: string; videoMode: VideoEnhancement; imageMode: ImageEnhancement; platform: string; arch: string; version: string; mpv: boolean; image: boolean }
export interface DesktopPlayback { running: boolean; paused: boolean; position: number; duration: number; droppedFrames: number; hwdec: string; ended: boolean; mode: VideoEnhancement; error: string }
export interface DesktopBridge {
 configuration(): Promise<DesktopConfiguration>
 connect(server: string): Promise<DesktopConfiguration>
 chooseEngine(kind: 'mpv' | 'image'): Promise<DesktopConfiguration>
 setPreferences(value: { videoMode: VideoEnhancement; imageMode: ImageEnhancement }): Promise<DesktopConfiguration>
 openVideo(value: { url: string; start: number; title: string }): Promise<DesktopPlayback>
 controlVideo(action: 'pause' | 'seek' | 'fullscreen' | 'mode', value?: number | VideoEnhancement): Promise<DesktopPlayback>
 videoState(): Promise<DesktopPlayback>
 stopVideo(): Promise<void>
 enhanceImage(value: { url: string; mode: 'anime' | 'photo' }): Promise<{ url: string; cached: boolean; scale: number }>
}
declare global { interface Window { heDesktop?: DesktopBridge } }
export const desktopBridge = window.heDesktop
export const desktopState = reactive<DesktopConfiguration>({ server: '', videoMode: 'off', imageMode: 'off', platform: '', arch: '', version: '', mpv: false, image: false })
export async function initDesktop() {
 if (desktopBridge) {
  document.documentElement.classList.add('he-desktop')
  Object.assign(desktopState, await desktopBridge.configuration())
 }
}
export async function setDesktopPreferences(videoMode: VideoEnhancement, imageMode: ImageEnhancement) {
 if (desktopBridge) Object.assign(desktopState, await desktopBridge.setPreferences({ videoMode, imageMode }))
}
