import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, reactive, ref } from 'vue'
vi.mock('../desktop', () => ({ desktopBridge: {}, desktopState: reactive({ imageMode: 'off', videoMode: 'off' }), desktopSession: reactive({ generation: 'visible-one', server: 'https://reader.example' }), setDesktopPreferences: vi.fn() }))
import MangaReader from '../components/media-detail/MangaReader.vue'
import { desktopSession } from '../desktop'
import { authState } from '../auth'
import { useMediaProgress } from '../composables/useMediaProgress'
import type { Media } from '../types'
class ControlledImage {
  static instances: ControlledImage[] = []
  src = ''; decoding = ''; naturalWidth = 480; naturalHeight = 720
  onload: (() => Promise<void>) | null = null
  onerror: (() => void) | null = null
  decode = vi.fn().mockResolvedValue(undefined)
  constructor() { ControlledImage.instances.push(this) }
}
const wrappers: ReturnType<typeof mount>[] = []
const frames = new Map<number, FrameRequestCallback>(); let frameId = 0
const box = (top = 0, height = 600, left = 0, width = 800) => ({ x: left, y: top, top, bottom: top + height, left, right: left + width, width, height, toJSON: () => ({}) } as DOMRect)
const rectangle = (element: Element, get: () => DOMRect) => vi.spyOn(element, 'getBoundingClientRect').mockImplementation(get)
function loaded(image: HTMLImageElement, get = () => box()) {
  Object.defineProperties(image, { complete: { value: true, configurable: true }, naturalWidth: { value: 480, configurable: true } })
  rectangle(image, get)
}
function paint() { for (let count = 0; count < 2; count++) { const next = [...frames.values()]; frames.clear(); for (const callback of next) callback(0) } }
async function finish(index: number) { await ControlledImage.instances[index]!.onload!(); await flushPromises() }
function create() {
  const wrapper = mount(MangaReader, { props: { media: { id: 7, title: 'Reader', media_type: 'manga' } as Media, currentPage: 0, totalPages: 4, pageDimensions: [], showControls: false, clickOnlyControls: true, progressText: '1 / 4', progressPercent: 25 }, attachTo: document.body })
  wrappers.push(wrapper); return wrapper
}
beforeEach(() => {
  frames.clear(); ControlledImage.instances = []; localStorage.clear()
  desktopSession.generation = 'visible-one'; authState.user = { id: 1, username: 'test', is_active: true, is_admin: false, created_at: '' }
  vi.stubGlobal('Image', ControlledImage)
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { const id = ++frameId; frames.set(id, callback); return id })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id))
})
afterEach(() => { for (const wrapper of wrappers.splice(0)) wrapper.unmount(); vi.unstubAllGlobals(); vi.restoreAllMocks(); frames.clear(); document.body.innerHTML = '' })
it('does not report decoder prefetch or an unloaded DOM image; a displayed cache hit uses the same path', async () => {
  const wrapper = create(); await finish(0); await finish(1)
  const container = wrapper.get('.he-pager').element
  rectangle(container, () => box())
  paint(); expect(wrapper.emitted('visiblePage')).toBeUndefined()
  loaded(wrapper.get('.he-reader-canvas-page img').element as HTMLImageElement)
  await wrapper.get('.he-reader-canvas-page img').trigger('load'); paint()
  expect(wrapper.emitted('visiblePage')).toEqual([[7, 0]])
  await wrapper.setProps({ currentPage: 1 }); await flushPromises()
  loaded(wrapper.get('.he-reader-canvas-page img').element as HTMLImageElement)
  paint() // Cached DOM image needs no second network/load notification.
  expect(wrapper.emitted('visiblePage')?.at(-1)).toEqual([7, 1])
})
it('reports the largest displayed server index for an RTL spread and ignores an obsolete identity', async () => {
  localStorage.setItem('he_manga_read_mode', 'double'); localStorage.setItem('he_manga_rtl', 'true')
  const wrapper = create(); await finish(0); await finish(1)
  const container = wrapper.get('.he-pager').element
  rectangle(container, () => box())
  wrapper.findAll('.he-reader-canvas-page img').forEach((image, index) => loaded(image.element as HTMLImageElement, () => box(0, 600, index * 400, 400)))
  paint(); expect(wrapper.emitted('visiblePage')).toEqual([[7, 1]])
  await wrapper.setProps({ currentPage: 2 }); await flushPromises()
  desktopSession.generation = 'visible-two'
  await finish(2); await finish(3)
  wrapper.findAll('.he-reader-canvas-page img').forEach(image => loaded(image.element as HTMLImageElement))
  paint(); (wrapper.vm as any).flushVisiblePage()
  expect(wrapper.emitted('visiblePage')).toEqual([[7, 1]])
})
it('uses the webtoon viewport middle, but submits the last visible page at the document bottom', async () => {
  localStorage.setItem('he_manga_read_mode', 'webtoon')
  const wrapper = create(); for (let index = 0; index < 4; index++) await finish(index)
  const pages = wrapper.findAll('.he-reader-page'), container = wrapper.find({ ref: 'webtoonContainerRef' }).element as HTMLElement
  rectangle(container, () => box())
  Object.defineProperties(container, { clientHeight: { value: 600, configurable: true }, scrollHeight: { value: 1150, configurable: true } })
  pages.forEach((page, index) => {
    const get = () => box(index * 350 - container.scrollTop, index === 3 ? 100 : 350)
    rectangle(page.element, get); loaded(page.get('img').element as HTMLImageElement, get)
  })
  container.scrollTop = 0; paint(); expect(wrapper.emitted('visiblePage')?.at(-1)).toEqual([7, 0])
  container.scrollTop = 450; container.dispatchEvent(new Event('scroll')); paint()
  expect(wrapper.emitted('visiblePage')?.at(-1)).toEqual([7, 2])
  container.scrollTop = 550; container.dispatchEvent(new Event('scroll')); paint()
  expect(wrapper.emitted('visiblePage')?.at(-1)).toEqual([7, 3])
})
it('saves only confirmed visible manga pages, including a close while the next page is still loading', async () => {
  const currentPage = ref(2), media = ref({ id: 7, media_type: 'manga', progress: 0, page_count: 4, view_status: 'viewing' } as Media)
  const update = vi.fn().mockResolvedValue(undefined); let progress!: ReturnType<typeof useMediaProgress>
  wrappers.push(mount(defineComponent({ setup() {
    progress = useMediaProgress({ media, currentPage, totalMangaPages: ref(4), isVideo: computed(() => false), isManga: computed(() => true), visibleMangaOnly: true, updateMedia: update, emitUpdated: () => {}, onVideoEnded: () => {} })
    return {}
  }, template: '<div />' })))
  await progress.flushProgress(); expect(update).not.toHaveBeenCalled()
  progress.visiblePage(0); await progress.flushProgress(); expect(update).toHaveBeenLastCalledWith({ progress: 0 }, 7)
  currentPage.value = 3; await flushPromises(); await progress.flushProgress()
  expect(update).toHaveBeenLastCalledWith({ progress: 0 }, 7)
  progress.visiblePage(3); await progress.flushProgress(); expect(update).toHaveBeenLastCalledWith({ progress: 3 }, 7)
})
