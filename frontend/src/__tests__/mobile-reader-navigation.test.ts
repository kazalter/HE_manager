import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'
import HomeView from '../views/HomeView.vue'
import MangaReader from '../components/media-detail/MangaReader.vue'
import { authState } from '../auth'
import type { Media } from '../types'

// Keep Home -> verification -> detail -> reader real: a component-only reader
// test cannot catch the parent destroying it on every scroll progress update.
vi.mock('../components/asyncComponents', async () => ({
  AsyncMediaDetail: (await import('../components/VerifiedMediaDetail.vue')).default,
}))
class ControlledImage {
  static instances: ControlledImage[] = []
  src = ''; decoding = ''; naturalWidth = 800; naturalHeight = 1200
  onload: (() => Promise<void>) | null = null
  onerror: (() => void) | null = null
  decode = vi.fn().mockResolvedValue(undefined)
  constructor() { ControlledImage.instances.push(this) }
}
const images = Array.from({ length: 5 }, (_, index): Media => ({
  id: index + 1, title: `Image ${index + 1}`, media_type: 'image',
  width: 800, height: 1200, tags: [], progress: 0, view_status: 'viewing',
  is_missing: false, file_size: 1000, relative_path: `${index + 1}.jpg`,
  extension: '.jpg', cover_path: null, duration: null, page_count: null,
  rating: 0, favorite: false, last_opened_at: null, source_url: null,
  source_site: null, missing_since: null, created_at: '2026-10-24',
}))
const frames = new Map<number, FrameRequestCallback>()
let frame = 0, wrapper: ReturnType<typeof mount> | undefined
const originalWidth = window.innerWidth
const response = (data: unknown) => ({ data, headers: { 'x-total-count': '5' } })
beforeEach(() => {
  vi.useFakeTimers(); localStorage.clear(); frames.clear(); ControlledImage.instances = []
  window.innerWidth = 390
  authState.token = 'mobile-reader-test'
  authState.user = { id: 1, username: 'reader', is_active: true, is_admin: false, created_at: '' }
  vi.stubGlobal('Image', ControlledImage)
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.set(++frame, callback); return frame })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id))
})
afterEach(() => {
  wrapper?.unmount(); wrapper = undefined
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); localStorage.clear()
  window.innerWidth = originalWidth; document.body.innerHTML = ''
})
async function create() {
  const pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: unknown) => void; signal: AbortSignal }>()
  const get = vi.spyOn(axios, 'get').mockImplementation(async (url, config: any) => {
    if (url === '/tags') return response([])
    if (url === '/media') return response(config?.params?.sort === 'opened' ? [] : images)
    if (url === '/media/1') return response(images[0])
    const id = Number(String(url).split('/').at(-1))
    return new Promise((resolve, reject) => { pending.set(id, { resolve, reject, signal: config.signal }) }) as any
  })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push('/type/image'); await router.isReady()
  wrapper = mount(HomeView, { props: { mediaType: 'image' }, attachTo: document.body, global: {
    plugins: [router], stubs: {
      MediaCard: defineComponent({ props: ['media'], emits: ['click'], template: '<button class="test-card" @click="$emit(\'click\')">{{ media.title }}</button>' }),
      DiscardContentDialog: true,
    },
  } })
  await flushPromises()
  await wrapper.get('.test-card').trigger('click'); await flushPromises()
  const reader = wrapper.getComponent(MangaReader)
  const viewport = reader.find({ ref: 'webtoonContainerRef' })
  const container = viewport.element as HTMLElement
  Object.defineProperties(container, { clientHeight: { value: 600 }, scrollHeight: { value: 5000 } })
  Array.from(container.querySelectorAll('.he-reader-page')).forEach((child, index) => {
    Object.defineProperties(child, { offsetTop: { value: index * 1000 }, offsetHeight: { value: 1000 } })
  })
  // Hide controls by tapping, then let the initial scroll lock expire.
  await viewport.trigger('click'); vi.advanceTimersByTime(250); await flushPromises()
  const scroll = async (top: number) => {
    container.scrollTop = top
    await viewport.trigger('scroll')
    const callbacks = [...frames.values()]; frames.clear()
    callbacks.forEach(callback => callback(0))
    await flushPromises()
  }
  return { router, reader, viewport, container, scroll, pending, get }
}

it('toggles image autoplay with Space, ignores repeats and preserves editing and button keys', async () => {
  await create()
  const press = (target: EventTarget = window, options: KeyboardEventInit = {}) => {
    const event = new KeyboardEvent('keydown', { key: ' ', code: 'Space', bubbles: true, cancelable: true, ...options })
    target.dispatchEvent(event)
    return event
  }
  expect(press().defaultPrevented).toBe(true)
  await flushPromises()
  expect(!!document.querySelector('button[aria-label="暂停自动播放"]')).toBe(true)
  press(window, { repeat: true })
  const input = document.querySelector('input[aria-label="自动播放间隔，秒"]')!
  expect(press(input).defaultPrevented).toBe(false)
  expect(press(document.querySelector('button[aria-label="暂停自动播放"]')!).defaultPrevented).toBe(false)
  expect(press(window, { ctrlKey: true }).defaultPrevented).toBe(false)
  await flushPromises()
  expect(!!document.querySelector('button[aria-label="暂停自动播放"]')).toBe(true)
  press()
  await flushPromises()
  expect(!!document.querySelector('button[aria-label="开始自动播放"]')).toBe(true)
})

it('keeps the actual mobile reader, scroll offset and hidden controls alive across delayed and out-of-order route verification', async () => {
  const { router, reader, container, scroll, pending } = await create()
  await ControlledImage.instances[0]!.onload!(); await flushPromises()
  const displayedImage = reader.get('#webtoon-page-0 img').element
  const readerRoot = reader.element
  const scrollTo = vi.spyOn(container, 'scrollTo')
  await scroll(1100)
  expect(router.currentRoute.value.query.media).toBe('2')
  expect(pending.has(2)).toBe(true)
  expect(wrapper!.getComponent(MangaReader).element).toBe(readerRoot)
  expect(reader.get('.he-manga-controls').attributes('inert')).toBeDefined()
  expect(document.body.textContent).not.toContain('正在打开作品')
  await scroll(2100)
  expect(router.currentRoute.value.query.media).toBe('3')
  expect(pending.get(2)!.signal.aborted).toBe(true)
  pending.get(3)!.resolve(response(images[2])); await flushPromises()
  pending.get(2)!.resolve(response(images[1])); await flushPromises()
  expect(wrapper!.getComponent(MangaReader).element).toBe(readerRoot)
  expect(reader.props('currentPage')).toBe(2)
  expect(reader.get('#webtoon-page-0 img').element).toBe(displayedImage)
  expect(container.scrollTop).toBe(2100)
  expect(scrollTo).not.toHaveBeenCalled()
  expect(reader.get('.he-manga-controls').attributes('inert')).toBeDefined()
  // Browser route navigation reuses the reader and synchronizes its selected page.
  await router.replace('/type/image?media=1'); await flushPromises()
  expect(wrapper!.getComponent(MangaReader).element).toBe(readerRoot)
  expect(reader.props('currentPage')).toBe(0)
  // Returning to the last verified image must also work before the next GET ends.
  vi.advanceTimersByTime(110)
  await scroll(1100)
  await router.replace('/type/image?media=1'); await flushPromises()
  expect(pending.get(2)!.signal.aborted).toBe(true)
  expect(reader.props('currentPage')).toBe(0)
  pending.get(2)!.resolve(response(images[1])); await flushPromises()
  expect(reader.props('currentPage')).toBe(0)
  expect(wrapper!.getComponent(MangaReader).element).toBe(readerRoot)
})

it('closes on failed background verification and ignores a response arriving after close', async () => {
  const { router, scroll, pending } = await create()
  await scroll(1100)
  pending.get(2)!.reject({ response: { status: 404 } }); await flushPromises()
  expect(wrapper!.findComponent(MangaReader).exists()).toBe(false)
  expect(router.currentRoute.value.query.media).toBeUndefined()
  expect(document.body.textContent).toContain('作品已不存在')
  await wrapper!.get('.test-card').trigger('click'); await flushPromises()
  await router.replace('/type/image?media=3'); await flushPromises()
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); await flushPromises()
  expect(pending.get(3)!.signal.aborted).toBe(true)
  pending.get(3)!.resolve(response(images[2])); await flushPromises()
  expect(wrapper!.findComponent(MangaReader).exists()).toBe(false)
  expect(router.currentRoute.value.query.media).toBeUndefined()
})
