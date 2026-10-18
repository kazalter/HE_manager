import type { User } from './types'
/** Page-facing capabilities. Native modules, file paths and texture handles stay in the host. */
export type VideoEnhancement = 'off' | 'efficiency' | 'quality'
export type ImageEnhancement = 'off' | 'anime' | 'photo'
export interface DesktopConfiguration {
  server: string; videoMode: VideoEnhancement; imageMode: ImageEnhancement
  platform: string; arch: string; version: string; mpv: boolean; image: boolean
  videoPresentation: 'embedded'
}
export interface DesktopSessionSnapshot {
  server: string; generation: string; revision: number; user: User | null
  hasUsers: boolean; error: string; persistent: boolean; restoring: boolean
}
export interface DesktopTrack { id: number; type: 'audio' | 'sub'; title: string; language: string; selected: boolean }
export interface DesktopPlayback {
  running: boolean; paused: boolean; position: number; duration: number; droppedFrames: number
  hwdec: string; ended: boolean; mode: VideoEnhancement; error: string
  loading: boolean; buffering: boolean; tracks: DesktopTrack[]; aid: string; sid: string
  speed: number; volume: number; generation: number; fullscreen: boolean
}
export interface PlayerSessionState {
  activeKind: 'none' | 'video' | 'audio'
  activeMedia: { type: string; id?: number; title?: string; url?: string; start?: number } | null
  videoRunning: boolean
  videoPaused: boolean
  videoPosition: number
  videoDuration: number
  videoDroppedFrames: number
}
export type DesktopVideoAction = 'pause' | 'seek' | 'seek-to' | 'fullscreen' | 'exit-fullscreen' | 'audio-track' | 'subtitle-track' | 'speed' | 'volume'
export interface DesktopBridge {
  configuration(): Promise<DesktopConfiguration>
  authentication(): Promise<DesktopSessionSnapshot>
  login(value: { username: string; password: string; bootstrap?: boolean }): Promise<DesktopSessionSnapshot>
  logout(): Promise<DesktopSessionSnapshot>
  restoreLogin(): Promise<DesktopSessionSnapshot>
  retryProgress(): Promise<void>
  onBeforeClose(callback: () => void | Promise<void>): () => void
  onSessionChanged(callback: (snapshot: DesktopSessionSnapshot) => void): () => void
  connect(server: string): Promise<DesktopConfiguration>
  chooseEngine(kind: 'mpv' | 'image'): Promise<DesktopConfiguration>
  setPreferences(value: { videoMode: VideoEnhancement; imageMode: ImageEnhancement }): Promise<DesktopConfiguration>
  openVideo(value: { url: string; start: number; title: string }): Promise<DesktopPlayback>
  controlVideo(action: 'pause' | 'fullscreen' | 'exit-fullscreen'): Promise<DesktopPlayback>
  controlVideo(action: 'seek' | 'seek-to' | 'audio-track' | 'subtitle-track' | 'speed' | 'volume', value: number): Promise<DesktopPlayback>
  videoState(): Promise<DesktopPlayback>
  stopVideo(generation?: string): Promise<void>
  notifyAudioStart?(options?: { mediaId?: number; title?: string; url?: string; trackIndex?: number }): Promise<void>
  notifyAudioStop?(): Promise<void>
  playerSessionState?(): Promise<PlayerSessionState>
  onPlayerSessionChanged?(callback: (state: PlayerSessionState) => void): () => void
  mountVideoSurface(id: string): void
  unmountVideoSurface(): void
  enhanceImage(value: { url: string; mode: 'anime' | 'photo' }): Promise<{ url: string; cached: boolean; scale: number }>
  isFullscreen?(): Promise<boolean>
  toggleFullscreen?(): Promise<boolean>
  exitFullscreen?(): Promise<boolean>
}

