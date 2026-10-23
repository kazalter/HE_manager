import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import MangaReader from '../components/media-detail/MangaReader.vue'
import { useReaderImageBuffer } from '../composables/useReaderImageBuffer'
import { readerImageWindow } from '../utils/readerImageWindow'
import type { Media } from '../types'

class ControlledImage {
  static instances: ControlledImage[] = []
  src = ''; decoding = ''; fetchPriority = ''; naturalWidth = 800; naturalHeight = 1200
  onload: (() => Promise<void>) | null = null
  onerror: (() => void) | null = null
  decode = vi.fn().mockResolvedValue(undefined)
  constructor() { ControlledImage.instances.push(this) }
}
let wrapper: ReturnType<typeof mount> | undefined
afterEach(() => {
  wrapper?.unmount(); wrapper = undefined
  vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); localStorage.clear()
  ControlledImage.instances = []
})
const finish = async (index: number) => { await ControlledImage.instances[index]!.onload!(); await flushPromises() }

it('retains decoded history outside the prefetch window and reuses it without another load or decode', async () => {
  vi.stubGlobal('Image', ControlledImage)
  const buffer = useReaderImageBuffer()
  buffer.requestWindow(['0', '1', '2'])
  for (let index = 0; index < 3; index++) await finish(index)
  buffer.requestWindow(['10']); await finish(3)
  expect(buffer.isDecoded('0')).toBe(true)
  buffer.requestWindow(['0', '1', '2'])
  expect(ControlledImage.instances).toHaveLength(4)
  expect(ControlledImage.instances[0]!.decode).toHaveBeenCalledOnce()
  expect(buffer.isDecoded('0')).toBe(true)
  buffer.dispose()
})

it('bounds bitmap memory and rewarms an evicted page instead of trusting its old ready flag', async () => {
  vi.stubGlobal('Image', ControlledImage)
  const buffer = useReaderImageBuffer(undefined, { maxBytes: 800 * 1200 * 4 * 2, maxImages: 2 })
  buffer.requestWindow(['0', '1']); await finish(0); await finish(1)
  buffer.requestWindow(['2']); await finish(2)
  expect(buffer.states.get('0')?.status).toBe('ready')
  expect(buffer.isDecoded('0')).toBe(false)
  buffer.requestWindow(['0'])
  expect(buffer.isResident('0')).toBe(true)
  expect(buffer.isDecoded('0')).toBe(false)
  expect(ControlledImage.instances[3]!.src).toBe('0')
  await finish(3)
  expect(buffer.isDecoded('0')).toBe(true)
  expect([...buffer.states.keys()].filter(buffer.isDecoded)).toHaveLength(2)
  buffer.clear()
  expect(buffer.isResident('0')).toBe(false)
  buffer.dispose()
})

it('ignores a canceled decode after jumping to a different window', async () => {
  vi.stubGlobal('Image', ControlledImage)
  const buffer = useReaderImageBuffer()
  buffer.requestWindow(['0'])
  let decoded!: () => void
  ControlledImage.instances[0]!.decode.mockImplementation(() => new Promise<void>(resolve => { decoded = resolve }))
  const oldLoad = ControlledImage.instances[0]!.onload!(); await flushPromises()
  buffer.requestWindow(['20'])
  decoded(); await oldLoad
  expect(buffer.isDecoded('0')).toBe(false)
  expect(buffer.isResident('0')).toBe(false)
  expect(buffer.states.has('0')).toBe(false)
  await finish(1)
  expect(buffer.isDecoded('20')).toBe(true)
  buffer.dispose()
})

it('prioritizes every visible page and keeps prefetch balanced when reversing direction', () => {
  const down = readerImageWindow(40, 10, 14, 1, () => [800, 1200])
  const up = readerImageWindow(40, 10, 14, -1, () => [800, 1200])
  expect(down.visibleCount).toBe(5)
  expect(down.indices.slice(0, 5)).toEqual([10, 11, 12, 13, 14])
  expect(down.indices.slice(5, 9)).toEqual([15, 9, 16, 8])
  expect(up.indices.slice(5, 9)).toEqual([9, 15, 8, 16])
  expect(new Set(up.indices)).toEqual(new Set(down.indices))
  const large = readerImageWindow(100, 50, 50, 1, () => [3000, 4000])
  expect(large.indices).toEqual([50, 51, 49])
})

it('mounts the scrolling image before decode finishes and preserves the same DOM image on a normal return', async () => {
  vi.stubGlobal('Image', ControlledImage)
  localStorage.setItem('he_image_read_mode', 'webtoon')
  localStorage.setItem('he_image_read_mode_mobile', 'webtoon')
  const pages = Array.from({ length: 20 }, (_, id) => ({ id: id + 100, title: `${id}`, media_type: 'image' })) as Media[]
  wrapper = mount(MangaReader, { props: { media: pages[0]!, imagePages: pages, currentPage: 0,
    totalPages: 20, pageDimensions: pages.map((): [number, number] => [800, 1200]), showControls: false, clickOnlyControls: true,
    progressText: '1 / 20', progressPercent: 5 } })
  const image = wrapper.get('#webtoon-page-0 img').element
  expect(wrapper.get('#webtoon-page-0').attributes('aria-busy')).toBe('true')
  await finish(0)
  expect(wrapper.get('#webtoon-page-0 img').element).toBe(image)
  await wrapper.setProps({ currentPage: 7 })
  expect(wrapper.get('#webtoon-page-0 img').element).toBe(image)
  await wrapper.setProps({ currentPage: 0 })
  expect(wrapper.get('#webtoon-page-0 img').element).toBe(image)
  expect(ControlledImage.instances.filter(img => img.src.includes('/stream/100'))).toHaveLength(1)
  expect(wrapper.text()).not.toContain('正在加载')
})

it('warms all viewport edges before offscreen pages even when several short images fit on screen', async () => {
  vi.stubGlobal('Image', ControlledImage); vi.useFakeTimers()
  const frames = new Map<number, FrameRequestCallback>(); let frameId = 0
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.set(++frameId, callback); return frameId })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id))
  localStorage.setItem('he_image_read_mode', 'webtoon'); localStorage.setItem('he_image_read_mode_mobile', 'webtoon')
  const pages = Array.from({ length: 20 }, (_, id) => ({ id: id + 100, title: `${id}`, media_type: 'image' })) as Media[]
  wrapper = mount(MangaReader, { props: { media: pages[0]!, imagePages: pages, currentPage: 0,
    totalPages: 20, pageDimensions: [], showControls: false, clickOnlyControls: true,
    progressText: '', progressPercent: 0 } })
  await flushPromises(); vi.advanceTimersByTime(110)
  const viewport = wrapper.find({ ref: 'webtoonContainerRef' }), container = viewport.element as HTMLElement
  Object.defineProperties(container, { clientHeight: { value: 900 }, scrollHeight: { value: 6000 } })
  Array.from(container.children).forEach((child, index) => {
    Object.defineProperties(child, { offsetTop: { value: index * 300 }, offsetHeight: { value: 300 } })
  })
  container.scrollTop = 1501
  await viewport.trigger('scroll')
  const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach(callback => callback(0))
  await flushPromises()
  expect(ControlledImage.instances.filter(image => image.src).map(image => image.src).slice(-3)).toEqual(['/stream/105', '/stream/106', '/stream/107'])
  expect(ControlledImage.instances.slice(-3).every(image => image.fetchPriority === 'high')).toBe(true)
})
