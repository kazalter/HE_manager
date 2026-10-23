import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'

const bridge = vi.hoisted(() => ({
  openVideo: vi.fn().mockResolvedValue({}),
  videoState: vi.fn().mockResolvedValue({}),
  stopVideo: vi.fn().mockResolvedValue(undefined),
  controlVideo: vi.fn().mockResolvedValue({}),
  mountVideoSurface: vi.fn(),
  unmountVideoSurface: vi.fn(),
  notifyAudioStop: vi.fn().mockResolvedValue(undefined),
  connect: vi.fn().mockResolvedValue({}),
  configuration: vi.fn().mockResolvedValue({}),
  chooseEngine: vi.fn().mockResolvedValue({}),
  setPreferences: vi.fn().mockResolvedValue({}),
  toggleFullscreen: vi.fn().mockResolvedValue(false),
  isFullscreen: vi.fn().mockResolvedValue(false),
  exitFullscreen: vi.fn().mockResolvedValue(false),
  onBeforeClose: vi.fn().mockReturnValue(() => {}),
}))

vi.mock('../desktop', () => ({
  desktopBridge: bridge,
  desktopSession: reactive({
    server: 'http://192.168.0.101:8011',
    generation: 'test-gen-1',
    revision: 1,
    user: null,
    hasUsers: true,
    error: '',
    persistent: false,
    restoring: false,
  }),
  desktopState: reactive({
    server: 'http://192.168.0.101:8011',
    videoMode: 'off',
    imageMode: 'off',
    platform: 'darwin',
    arch: 'arm64',
    version: '1.0.1',
    mpv: true,
    image: true,
    videoPresentation: 'embedded',
  }),
  setDesktopPreferences: vi.fn(),
}))

vi.mock('../stores/audioPlaybackStore', () => ({
  audioPlaybackStore: {
    state: { playing: false, media: null },
    togglePlay: vi.fn(),
    stop: vi.fn(),
  },
}))

import DesktopVideoPlayer from '../components/media-detail/DesktopVideoPlayer.vue'
import DesktopToolbar from '../components/DesktopToolbar.vue'
import MediaDetail from '../components/MediaDetail.vue'
import router from '../router/index'

const playback = (position = 5) => ({
  running: true,
  paused: true,
  position,
  duration: 60,
  droppedFrames: 0,
  hwdec: 'test',
  ended: false,
  mode: 'off',
  error: '',
  loading: false,
  buffering: false,
  tracks: [{ id: 1, type: 'audio', title: '国语' }, { id: 2, type: 'sub', title: '中文字幕' }],
  aid: '1',
  sid: '2',
  speed: 1,
  volume: 75,
  generation: 1,
  fullscreen: false,
})

const wrappers: ReturnType<typeof mount>[] = []

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

describe('ui-audit desktop coverage', () => {
  it('DesktopVideoPlayer handles ArrowLeft, ArrowRight, J, L, 0 shortcuts and auto-focuses canvas on mount', async () => {
    bridge.videoState.mockResolvedValue(playback(15))
    bridge.openVideo.mockResolvedValue(playback(15))
    bridge.controlVideo.mockResolvedValue(playback(15))

    const wrapper = mount(DesktopVideoPlayer, {
      props: { url: '/stream/10', title: '快捷键测试', start: 15 },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await flushPromises()

    const canvas = wrapper.get('canvas')
    expect(canvas.attributes('id')).toBeTruthy()
    expect(bridge.mountVideoSurface).toHaveBeenCalledWith(canvas.attributes('id'))

    // Test ArrowRight seek forward (+10s)
    await canvas.trigger('keydown', { key: 'ArrowRight' })
    expect(bridge.controlVideo).toHaveBeenLastCalledWith('seek', 10)

    // Test ArrowLeft seek backward (-10s)
    await canvas.trigger('keydown', { key: 'ArrowLeft' })
    expect(bridge.controlVideo).toHaveBeenLastCalledWith('seek', -10)

    // Test 'l' forward (+10s)
    await canvas.trigger('keydown', { key: 'l' })
    expect(bridge.controlVideo).toHaveBeenLastCalledWith('seek', 10)

    // Test 'j' backward (-10s)
    await canvas.trigger('keydown', { key: 'j' })
    expect(bridge.controlVideo).toHaveBeenLastCalledWith('seek', -10)

    // Test '0' seek to beginning (0s)
    await canvas.trigger('keydown', { key: '0' })
    expect(bridge.controlVideo).toHaveBeenLastCalledWith('seek-to', 0)

    // Test 'm' mute
    await canvas.trigger('keydown', { key: 'm' })
    expect(bridge.controlVideo).toHaveBeenLastCalledWith('volume', 0)

    // Test 'f' fullscreen
    await canvas.trigger('keydown', { key: 'f' })
    expect(bridge.controlVideo).toHaveBeenLastCalledWith('fullscreen')
  })

  it('DesktopToolbar trims server input and rejects empty server', async () => {
    bridge.connect.mockResolvedValue({
      server: 'http://192.168.1.50:8010',
      videoMode: 'off',
      imageMode: 'off',
    })

    const wrapper = mount(DesktopToolbar, { attachTo: document.body })
    wrappers.push(wrapper)
    await flushPromises()

    // Open the settings modal
    await wrapper.get('button').trigger('click')
    await flushPromises()

    const input = document.querySelector('input[autocomplete="url"]') as HTMLInputElement
    expect(input).toBeTruthy()

    // Set server with spaces
    input.value = '   http://192.168.1.50:8010   '
    input.dispatchEvent(new Event('input'))
    await flushPromises()

    // Submit form
    const form = document.querySelector('form')!
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()

    // Verifies connect was called with trimmed URL
    expect(bridge.connect).toHaveBeenCalledWith('http://192.168.1.50:8010')

    // Empty input validation
    bridge.connect.mockClear()
    input.value = '   '
    input.dispatchEvent(new Event('input'))
    await flushPromises()
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(bridge.connect).not.toHaveBeenCalled()
  })

  it('MediaDetail window capture keydown protects repeat and ignores input/button focus', async () => {
    bridge.videoState.mockResolvedValue(playback(10))
    bridge.openVideo.mockResolvedValue(playback(10))
    bridge.controlVideo.mockResolvedValue(playback(10))

    const wrapper = mount(MediaDetail, {
      props: {
        initialMedia: {
          id: 101,
          title: '媒体详情按键测试',
          media_type: 'video',
          duration: 100,
          progress: 10,
          favorite: false,
          rating: 0,
          view_status: 'viewing',
          tags: [],
          source_url: '',
          source_site: '',
          cover_path: '',
          is_missing: false,
          created_at: '2026-01-01',
          extension: 'mp4',
          file_size: 1024 * 1024 * 10,
          width: 1920,
          height: 1080,
        } as any,
        allMedia: [],
      },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await flushPromises()

    // 1. Dispatch Space with repeat=false -> should trigger controlVideo('pause') exactly once
    bridge.controlVideo.mockClear()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', repeat: false, bubbles: true }))
    expect(bridge.controlVideo).toHaveBeenCalledTimes(1)
    expect(bridge.controlVideo).toHaveBeenCalledWith('pause')

    // 2. Dispatch Space with repeat=true (holding down) -> should NOT trigger another call
    bridge.controlVideo.mockClear()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', repeat: true, bubbles: true }))
    expect(bridge.controlVideo).not.toHaveBeenCalled()

    // 3. Dispatch 'f' with repeat=false -> triggers fullscreen once
    bridge.controlVideo.mockClear()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', repeat: false, bubbles: true }))
    expect(bridge.controlVideo).toHaveBeenCalledTimes(1)
    expect(bridge.controlVideo).toHaveBeenCalledWith('fullscreen')

    // 4. Dispatch 'f' with repeat=true -> should NOT trigger fullscreen again
    bridge.controlVideo.mockClear()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', repeat: true, bubbles: true }))
    expect(bridge.controlVideo).not.toHaveBeenCalled()

    // 5. Input focus: keydown inside an input must be ignored
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()
    bridge.controlVideo.mockClear()
    input.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', repeat: false, bubbles: true }))
    expect(bridge.controlVideo).not.toHaveBeenCalled()
    document.body.removeChild(input)

    // 6. Button focus: keydown inside a button must be ignored
    const button = document.createElement('button')
    document.body.appendChild(button)
    button.focus()
    bridge.controlVideo.mockClear()
    button.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', repeat: false, bubbles: true }))
    expect(bridge.controlVideo).not.toHaveBeenCalled()
    document.body.removeChild(button)
  })

  it('router includes catch-all wildcard redirecting to home', async () => {
    await router.push('/non-existent-random-route-404')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/')
  })
})
