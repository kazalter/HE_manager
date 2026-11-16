import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'

const mocks = vi.hoisted(() => ({ start: vi.fn(), state: vi.fn(), stop: vi.fn() }))
vi.mock('../desktop', () => ({
  desktopBridge: { wallpaperStart: mocks.start, wallpaperState: mocks.state, wallpaperStop: mocks.stop },
  desktopSession: reactive({ generation: 'test' }),
  desktopState: reactive({ platform: 'win32' }),
}))
import Live2dView from '../views/Live2dView.vue'
import { desktopState } from '../desktop'

afterEach(() => { vi.clearAllMocks(); desktopState.platform = 'win32' })

it('only enables wallpaper for a selected skin reported by the embedded viewer', async () => {
  mocks.state.mockResolvedValue({ running: false, modelId: '', pauseWhenCovered: true, playing: null })
  mocks.start.mockResolvedValue({ running: true, modelId: 'dafeng_6', pauseWhenCovered: true, playing: true })
  mocks.stop.mockResolvedValue({ running: false, modelId: '', pauseWhenCovered: true, playing: null })
  const wrapper = mount(Live2dView, { attachTo: document.body })
  await flushPromises()
  const button = wrapper.get('button')
  expect(button.attributes('disabled')).toBeDefined()
  window.dispatchEvent(new MessageEvent('message', { origin: 'https://other.example', source: wrapper.get('iframe').element.contentWindow, data: { type: 'l2d:model', id: 'unexpected' } }))
  await flushPromises()
  expect(button.attributes('disabled')).toBeDefined()
  window.dispatchEvent(new MessageEvent('message', { origin: window.location.origin, source: wrapper.get('iframe').element.contentWindow, data: { type: 'l2d:model', id: 'dafeng_6' } }))
  await flushPromises()
  expect(button.attributes('disabled')).toBeUndefined()
  await button.trigger('click'); await flushPromises()
  expect(mocks.start).toHaveBeenCalledWith('dafeng_6')
  expect(wrapper.text()).toContain('已设置为桌面壁纸')
  expect(wrapper.text()).toContain('壁纸运行中')
  const stopBtn = wrapper.findAll('button').find((b) => b.text().includes('停止壁纸'))
  expect(stopBtn).toBeDefined()
  await stopBtn!.trigger('click'); await flushPromises()
  expect(mocks.stop).toHaveBeenCalledOnce()
  expect(wrapper.text()).toContain('已停止桌面壁纸')
  wrapper.unmount()
})

it('does not show the wallpaper entry on other desktop platforms', () => {
  desktopState.platform = 'darwin'
  const wrapper = mount(Live2dView)
  expect(wrapper.text()).not.toContain('设为桌面壁纸')
  wrapper.unmount()
})
