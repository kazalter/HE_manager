import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
const mocks = vi.hoisted(() => ({
  state: vi.fn(), preferences: vi.fn(), stop: vi.fn(),
}))
vi.mock('../desktop', () => ({ desktopBridge: {
  wallpaperState: mocks.state, wallpaperPreferences: mocks.preferences, wallpaperStop: mocks.stop,
} }))
import WallpaperSettings from '../components/WallpaperSettings.vue'

afterEach(() => {
  vi.restoreAllMocks()
})

it('loads the current wallpaper, saves the pause setting, and stops the wallpaper', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [{ id: 'dafeng_6', name: '大凤-盛夏' }] }))
  const displays = [{ id: 1, label: '主屏', width: 1920, height: 1080, primary: true }, { id: 2, label: '副屏', width: 2560, height: 1440, primary: false }]
  mocks.state.mockResolvedValue({ running: true, modelId: 'dafeng_6', pauseWhenCovered: true, muted: true, keepInTray: true, autoRestore: true, displayId: 1, displays, playing: false })
  mocks.preferences.mockResolvedValue({ running: true, modelId: 'dafeng_6', pauseWhenCovered: false, muted: true, keepInTray: true, autoRestore: true, displayId: 1, displays, playing: true })
  mocks.stop.mockResolvedValue({ running: false, modelId: '', pauseWhenCovered: false, playing: null })
  const wrapper = mount(WallpaperSettings)
  await flushPromises()
  expect(wrapper.text()).toContain('大凤-盛夏 (dafeng_6)')
  expect(wrapper.text()).toContain('已暂停')
  await wrapper.get('input').setValue(false)
  await flushPromises()
  expect(mocks.preferences).toHaveBeenCalledWith({ pauseWhenCovered: false })
  expect(wrapper.text()).toContain('播放中')
  const checkboxes = wrapper.findAll('input[type="checkbox"]')
  await checkboxes[1].setValue(false)
  await flushPromises()
  expect(mocks.preferences).toHaveBeenCalledWith({ muted: false })
  await wrapper.get('select').setValue('2')
  await flushPromises()
  expect(mocks.preferences).toHaveBeenCalledWith({ displayId: 2 })
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(mocks.stop).toHaveBeenCalledOnce()
  expect(wrapper.text()).toContain('壁纸未运行')
  wrapper.unmount()
})
