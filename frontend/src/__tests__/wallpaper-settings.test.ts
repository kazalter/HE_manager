import { expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
const mocks = vi.hoisted(() => ({
  state: vi.fn(), preferences: vi.fn(), stop: vi.fn(),
}))
vi.mock('../desktop', () => ({ desktopBridge: {
  wallpaperState: mocks.state, wallpaperPreferences: mocks.preferences, wallpaperStop: mocks.stop,
} }))
import WallpaperSettings from '../components/WallpaperSettings.vue'

it('loads the current wallpaper, saves the pause setting, and stops the wallpaper', async () => {
  mocks.state.mockResolvedValue({ running: true, modelId: 'dafeng_6', pauseWhenCovered: true })
  mocks.preferences.mockResolvedValue({ running: true, modelId: 'dafeng_6', pauseWhenCovered: false })
  mocks.stop.mockResolvedValue({ running: false, modelId: '', pauseWhenCovered: false })
  const wrapper = mount(WallpaperSettings)
  await flushPromises()
  expect(wrapper.text()).toContain('dafeng_6')
  await wrapper.get('input').setValue(false)
  await flushPromises()
  expect(mocks.preferences).toHaveBeenCalledWith({ pauseWhenCovered: false })
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(mocks.stop).toHaveBeenCalledOnce()
  expect(wrapper.text()).toContain('壁纸未运行')
  wrapper.unmount()
})
