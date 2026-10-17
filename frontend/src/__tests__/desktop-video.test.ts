import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
const bridge = vi.hoisted(() => ({ openVideo: vi.fn(), videoState: vi.fn(), stopVideo: vi.fn(), controlVideo: vi.fn(), mountVideoSurface: vi.fn(), unmountVideoSurface: vi.fn() }))
vi.mock('../desktop', () => ({ desktopBridge: bridge, desktopState: reactive({ videoMode: 'off', imageMode: 'off' }), setDesktopPreferences: vi.fn() }))
vi.mock('../stores/audioPlaybackStore', () => ({ audioPlaybackStore: { state: { playing: false }, togglePlay: vi.fn() } }))
import DesktopVideoPlayer from '../components/media-detail/DesktopVideoPlayer.vue'
const playback = (position = 5) => ({ running: true, paused: true, position, duration: 30, droppedFrames: 0, hwdec: 'test', ended: false, mode: 'off', error: '', loading: false, buffering: false, tracks: [{ id: 1, type: 'audio', title: '第一音轨' }, { id: 2, type: 'sub', title: '日文字幕' }], aid: '1', sid: '2', speed: 1, volume: 75, generation: 1, fullscreen: false })
const wrappers: ReturnType<typeof mount>[] = []
const create = () => { const wrapper = mount(DesktopVideoPlayer, { props: { url: '/stream/1', title: '长标题测试视频', start: 5 }, attachTo: document.body }); wrappers.push(wrapper); return wrapper }
afterEach(() => { for (const wrapper of wrappers.splice(0)) wrapper.unmount(); vi.clearAllMocks(); document.body.innerHTML = '' })
function defaults() {
 bridge.videoState.mockResolvedValue(playback())
 bridge.openVideo.mockResolvedValue(playback())
 bridge.stopVideo.mockResolvedValue(undefined)
 bridge.controlVideo.mockResolvedValue(playback())
}
describe('embedded desktop video UI', () => {
 it('ignores a late open from the previous media and detaches its display on close', async () => {
  defaults()
  let complete: ((value: unknown) => void) | undefined
  bridge.openVideo.mockImplementationOnce(() => new Promise(resolve => { complete = resolve })).mockResolvedValue(playback(12))
  const wrapper = create()
  await wrapper.setProps({ url: '/stream/2' }); await flushPromises()
  complete!(playback(1)); await flushPromises()
  expect(wrapper.text()).toContain('0:12 / 0:30')
  expect(bridge.mountVideoSurface).toHaveBeenCalledWith(wrapper.get('canvas').attributes('id'))
  wrapper.unmount(); wrappers.splice(0)
  expect(bridge.unmountVideoSurface).toHaveBeenCalledOnce()
  expect(bridge.stopVideo).toHaveBeenCalledOnce()
  expect(wrapper.emitted('progress')?.at(-1)).toEqual([12, 30, false, true])
 })
 it('shows actual tracks, applies subtitle off, and closes its settings on Escape', async () => {
  defaults(); const wrapper = create(); await flushPromises()
  await wrapper.get('button[aria-label="播放设置"]').trigger('click'); await flushPromises()
  const dialog = document.querySelector('.ui-modal')!
  expect(dialog.textContent).toContain('第一音轨')
  expect(dialog.textContent).toContain('日文字幕')
  const subtitle = dialog.querySelectorAll('select')[1]!
  subtitle.value = '0'; subtitle.dispatchEvent(new Event('change', { bubbles: true })); await flushPromises()
  expect(bridge.controlVideo).toHaveBeenCalledWith('subtitle-track', 0)
  dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); await flushPromises()
  expect(document.querySelector('.ui-modal')).toBeNull()
  expect(bridge.stopVideo).not.toHaveBeenCalled()
 })
 it('keeps a retry available after opening fails and releases on unmount', async () => {
  defaults(); bridge.openVideo.mockRejectedValueOnce(new Error('无法连接服务器，请重试。'))
  const wrapper = create(); await flushPromises()
  expect(wrapper.text()).toContain('无法连接服务器，请重试。')
  const retry = wrapper.findAll('button').find(button => button.text() === '重新打开')!
  await retry.trigger('click'); await flushPromises()
  expect(bridge.openVideo).toHaveBeenCalledTimes(2)
  expect(wrapper.text()).not.toContain('视频暂时无法播放')
 })
})
