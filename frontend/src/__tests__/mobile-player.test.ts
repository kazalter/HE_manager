import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, ref } from 'vue'
import axios from 'axios'
import GlobalAudioPlayer from '../components/GlobalAudioPlayer.vue'
import { audioPlaybackStore as player } from '../stores/audioPlaybackStore'
import { useZoomScroller } from '../composables/useZoomScroller'
import { useMediaOverlayControls } from '../composables/useMediaOverlayControls'
import type { Media } from '../types'

const media = { id: 51, title: '音频作品', media_type: 'audio', cover_path: null, tags: [] } as unknown as Media
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.forEach(wrapper => wrapper.unmount()); wrappers.length = 0; player.stop(); vi.restoreAllMocks(); localStorage.clear(); document.body.innerHTML = '' })
describe('persistent audio and phone gestures', () => {
  it('retains the same audio element and source when minimized, then stops explicitly', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: { tracks: [{ index: 1, title: 'Track 1', lyrics: null }] } })
    vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
    const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
    player.open(media)
    const wrapper = mount(GlobalAudioPlayer, { attachTo: document.body })
    wrappers.push(wrapper)
    await vi.dynamicImportSettled()
    await flushPromises()
    const audio = document.querySelector('audio')!
    expect(audio).toBeTruthy()
    audio.dispatchEvent(new Event('play'))
    await flushPromises()
    expect(player.state.playing).toBe(true)
    player.minimize()
    await flushPromises()
    expect(document.querySelector('audio')).toBe(audio)
    expect(audio.getAttribute('src')).toContain('/audio/51/track/1')
    expect(pause).not.toHaveBeenCalled()
    expect(document.querySelector('button[aria-label="暂停音频"]')).toBeTruthy()
    player.stop()
    await flushPromises()
    expect(document.querySelector('audio')).toBeNull()
    expect(pause).toHaveBeenCalledOnce()
  })
  it('pinches without navigating and allows a deliberate swipe only at normal scale', () => {
    let zoom!: ReturnType<typeof useZoomScroller>
    const onSwipe = vi.fn()
    const scroller = document.createElement('div'), content = document.createElement('div')
    scroller.append(content)
    const frames: FrameRequestCallback[] = []
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => frames.push(callback))
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
    const settle = () => { for (let frame = 0, time = 0; frame < 300 && frames.length; frame++) frames.splice(0).forEach(callback => callback(time += 16)) }
    const wrapper = mount(defineComponent({ setup() {
      zoom = useZoomScroller({ scroller: ref(scroller), content: ref(content), centered: true, onSwipe, applyScale: (element, scale) => element.style.setProperty('--he-zoom', String(scale)) })
      return {}
    }, template: '<div />' }))
    const touch = (points: number[][], changed: number[][] = []) => ({ touches: points.map(([x, y]) => ({ clientX: x, clientY: y })), changedTouches: changed.map(([x, y]) => ({ clientX: x, clientY: y })), cancelable: true, preventDefault: vi.fn() }) as unknown as TouchEvent
    zoom.onTouchStart(touch([[100,100], [200,100]]))
    zoom.onTouchMove(touch([[50,100], [250,100]]))
    zoom.onTouchEnd(touch([], [[250,100]]))
    settle()
    expect(zoom.scale.value).toBe(2)
    expect(onSwipe).not.toHaveBeenCalled()
    expect(zoom.wasGesture()).toBe(true)
    // While zoomed a horizontal drag is the page's own native panning.
    zoom.onTouchStart(touch([[250,100]]))
    zoom.onTouchMove(touch([[100,110]]))
    zoom.onTouchEnd(touch([], [[100,110]]))
    expect(onSwipe).not.toHaveBeenCalled()
    zoom.reset()
    zoom.onTouchStart(touch([[250,100]]))
    zoom.onTouchMove(touch([[100,110]]))
    zoom.onTouchEnd(touch([], [[100,110]]))
    expect(onSwipe).toHaveBeenCalledWith(1)
    expect(zoom.wasGesture()).toBe(true)
    wrapper.unmount()
  })
  it('falls back to an immersive viewer if browser fullscreen is rejected', async () => {
    let controls!: ReturnType<typeof useMediaOverlayControls>
    Object.defineProperty(document.documentElement, 'requestFullscreen', { configurable: true, value: vi.fn().mockRejectedValue(new Error('unsupported')) })
    const wrapper = mount(defineComponent({ setup() { controls = useMediaOverlayControls(computed(() => false), computed(() => true)); return {} }, template: '<div />' }))
    await controls.toggleFullscreen()
    expect(controls.isFullscreen.value).toBe(true)
    delete (document.documentElement as unknown as Record<string, unknown>).requestFullscreen
    wrapper.unmount()
  })
})
