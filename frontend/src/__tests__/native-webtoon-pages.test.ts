import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import NativeWebtoonPages from '../components/media-detail/NativeWebtoonPages.vue'

let wrapper: ReturnType<typeof mount> | undefined
let images: HTMLImageElement[]
const pages = Array.from({ length: 60 }, (_, index) => ({ url: `/native-test/${index}.jpg`, width: 800, height: 1200, alt: `Page ${index}` }))
beforeEach(() => {
  vi.useFakeTimers(); images = []; vi.stubGlobal('innerWidth', 390)
  vi.stubGlobal('Image', function () {
    const image = document.createElement('img')
    Object.defineProperties(image, { naturalWidth: { value: 800 }, naturalHeight: { value: 1200 } })
    image.decode = vi.fn().mockResolvedValue(undefined)
    images.push(image); return image
  })
})
afterEach(() => { wrapper?.unmount(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
function create() {
  wrapper = mount(NativeWebtoonPages, { props: { pages, currentPage: 0 } })
  return wrapper
}
const finish = async (image: HTMLImageElement) => { image.onload?.(new Event('load')); await flushPromises() }
const warm = (page: number) => (wrapper!.vm as unknown as { warm: (page: number) => void }).warm(page)

it('preloads three preceding pages after a distant jump', async () => {
  create()
  warm(40)
  for (let index = 0; index < 8; index++) await finish(images[index]!)
  expect(images.slice(2, 9).map(image => image.getAttribute('src'))).toEqual([
    '/native-test/40.jpg', '/native-test/41.jpg', '/native-test/39.jpg',
    '/native-test/42.jpg', '/native-test/38.jpg', '/native-test/43.jpg', '/native-test/37.jpg',
  ])
})

it('reserves the whole book, downloads two at a time and displays the exact downloaded nodes without decode()', async () => {
  const view = create()
  expect(view.findAll('.he-reader-page')).toHaveLength(60)
  expect(view.get('#webtoon-page-59').attributes('style')).toContain('min-height: 585px')
  expect(images.map(image => image.getAttribute('src'))).toEqual(['/native-test/0.jpg', '/native-test/1.jpg'])
  const first = images[0]!
  await finish(first)
  expect(images).toHaveLength(3)
  expect(first.decode).not.toHaveBeenCalled()
  expect(view.get('#webtoon-page-0').find('img').exists()).toBe(false)
  vi.advanceTimersByTime(300)
  expect(view.get('#webtoon-page-0 img').element).toBe(first)
  warm(40)
  // Already downloaded pages are never torn down when the reading window moves.
  expect(view.get('#webtoon-page-0 img').element).toBe(first)
  await finish(images[1]!)
  expect(images[3]!.getAttribute('src')).toBe('/native-test/40.jpg')
  await finish(images[2]!)
  expect(images[4]!.getAttribute('src')).toBe('/native-test/41.jpg')
  await finish(images[3]!)
  expect(images[5]!.getAttribute('src')).toBe('/native-test/39.jpg')
})

it('retries a failed page, times out stalled requests, and ignores stale callbacks after a book change', async () => {
  const view = create()
  const stale = images[0]!.onload!
  images[0]!.onerror?.(new Event('error'))
  const slot = view.get('#webtoon-page-0')
  expect(slot.text()).toContain('图片加载失败')
  await slot.get('button').trigger('click')
  // The second inflight slot is released, and the retry takes priority.
  await finish(images[1]!)
  expect(images[3]!.getAttribute('src')).toBe('/native-test/0.jpg')
  vi.advanceTimersByTime(60_000)
  expect(slot.text()).toContain('图片加载失败')
  const pending = [...images].filter(image => image.onload)
  await view.setProps({ pages: [{ url: '/different.jpg', width: 100, height: 200, alt: 'New' }] })
  stale.call(images[0]!, new Event('load'))
  await flushPromises()
  expect(view.findAll('.he-reader-page')).toHaveLength(1)
  expect(view.find('img').exists()).toBe(false)
  for (const image of pending) expect(image.onload).toBeNull()
  const latest = images.at(-1)!
  const afterClose = latest.onload!
  view.unmount(); wrapper = undefined
  afterClose.call(latest, new Event('load'))
  vi.advanceTimersByTime(60_000)
  expect(latest.isConnected).toBe(false)
})

it('preserves space across rotation, uses original width for small images and compensates a corrected size above the viewport', async () => {
  const scroll = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  const view = create()
  const slot = view.get('#webtoon-page-0').element as HTMLElement
  vi.stubGlobal('scrollY', 1000)
  vi.spyOn(slot, 'getBoundingClientRect').mockReturnValue({ top: -1000 } as DOMRect)
  Object.defineProperty(slot, 'offsetHeight', { get: () => slot.querySelector('img') ? 600 : 585 })
  await finish(images[0]!)
  vi.advanceTimersByTime(300)
  expect(scroll).toHaveBeenCalledWith(0, 1015)
  vi.stubGlobal('innerWidth', 420); window.dispatchEvent(new Event('resize'))
  vi.advanceTimersByTime(200)
  expect(view.get('#webtoon-page-59').attributes('style')).toContain('min-height: 630px')
  expect(view.get('#webtoon-page-0').attributes('style')).toContain('min-height: 0px')
  await view.setProps({ pages: [{ url: '/small.jpg', width: 100, height: 200, alt: 'Small' }] })
  expect(view.get('#webtoon-page-0').attributes('style')).toContain('min-height: 200px')
})
