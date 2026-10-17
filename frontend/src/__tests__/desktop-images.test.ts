import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref, reactive } from 'vue'
const mocks = vi.hoisted(() => ({ enhanceImage: vi.fn() }))
vi.mock('../desktop', () => ({ desktopBridge: mocks, desktopState: reactive({ imageMode: 'anime' }) }))
import { useDesktopImageEnhancement } from '../composables/useDesktopImageEnhancement'
import { desktopState } from '../desktop'
afterEach(() => { vi.clearAllMocks(); desktopState.imageMode = 'anime' })
describe('desktop image enhancement', () => {
 it('keeps the original visible until a successful result and ignores stale pages', async () => {
  let complete: ((value: { url: string }) => void) | undefined
  mocks.enhanceImage.mockImplementationOnce(() => new Promise(resolve => { complete = resolve })).mockResolvedValue({ url: 'he://app/__cache/new.png' })
  const original = ref('/stream/1?token=test')
  const wrapper = mount(defineComponent({ setup() { const image = useDesktopImageEnhancement(() => [original.value]); return { image, original } }, template: '<img :src="image.displayUrl(original)">' }))
  expect(wrapper.get('img').attributes('src')).toBe('/stream/1?token=test')
  original.value = '/stream/2?token=test'
  await flushPromises()
  expect(wrapper.get('img').attributes('src')).toBe('he://app/__cache/new.png')
  complete!({ url: 'he://app/__cache/old.png' }); await flushPromises()
  expect(wrapper.get('img').attributes('src')).toBe('he://app/__cache/new.png')
  desktopState.imageMode = 'off'; await flushPromises()
  expect(wrapper.get('img').attributes('src')).toBe('/stream/2?token=test')
  wrapper.unmount()
 })
 it('continues displaying the original after a GPU failure', async () => {
  mocks.enhanceImage.mockRejectedValue(new Error('GPU unavailable'))
  const wrapper = mount(defineComponent({ setup() { return { image: useDesktopImageEnhancement(() => ['/stream/3']) } }, template: '<div><img :src="image.displayUrl(\'/stream/3\')"><p>{{ image.message.value }}</p></div>' }))
  await flushPromises()
  expect(wrapper.get('img').attributes('src')).toBe('/stream/3')
  expect(wrapper.text()).toContain('GPU unavailable')
  wrapper.unmount()
 })
 it('does not expose Electron IPC details after a cancelled request', async () => {
  mocks.enhanceImage.mockRejectedValue(new Error("Error invoking remote method 'he:image': Error: This operation was aborted"))
  const wrapper = mount(defineComponent({ setup() { return { image: useDesktopImageEnhancement(() => ['/stream/3']) } }, template: '<p>{{ image.message.value }}</p>' }))
  await flushPromises()
  expect(wrapper.text()).toContain('当前显示原图')
  expect(wrapper.text()).not.toContain('he:image')
  expect(wrapper.text()).not.toContain('Error invoking')
  wrapper.unmount()
 })

})
