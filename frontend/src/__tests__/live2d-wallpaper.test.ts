import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'

const mocks = vi.hoisted(() => ({ start: vi.fn() }))
vi.mock('../desktop', () => ({
  desktopBridge: { wallpaperStart: mocks.start },
  desktopSession: reactive({ generation: 'test' }),
  desktopState: reactive({ platform: 'win32' }),
}))
import Live2dView from '../views/Live2dView.vue'
import { desktopState } from '../desktop'

afterEach(() => { vi.clearAllMocks(); desktopState.platform = 'win32' })

it('only enables wallpaper for a selected skin reported by the embedded viewer', async () => {
  mocks.start.mockResolvedValue({ running: true })
  const wrapper = mount(Live2dView, { attachTo: document.body })
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
  wrapper.unmount()
})

it('does not show the wallpaper entry on other desktop platforms', () => {
  desktopState.platform = 'darwin'
  const wrapper = mount(Live2dView)
  expect(wrapper.text()).not.toContain('设为桌面壁纸')
  wrapper.unmount()
})
