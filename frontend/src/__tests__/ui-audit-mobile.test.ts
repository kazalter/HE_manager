import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'
import TopBar from '../components/TopBar.vue'
import MobileNavigation from '../components/MobileNavigation.vue'
import GlobalAudioPlayer from '../components/GlobalAudioPlayer.vue'
import AudioPlayer from '../components/media-detail/AudioPlayer.vue'
import MangaReader from '../components/media-detail/MangaReader.vue'
import { audioPlaybackStore } from '../stores/audioPlaybackStore'
import { useZoomScroller } from '../composables/useZoomScroller'
import type { Media, User } from '../types'

const sampleAudioMedia = {
  id: 101,
  title: '测试音频专辑',
  media_type: 'audio',
  cover_path: '/covers/audio1.jpg',
  tags: [],
} as unknown as Media

const sampleMangaMedia = {
  id: 202,
  title: '测试漫画作品',
  media_type: 'manga',
  cover_path: '/covers/manga1.jpg',
  tags: [],
} as unknown as Media

const wrappers: ReturnType<typeof mount>[] = []

const createTestRouter = (initialPath = '/') => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div>Home</div>' } },
      { path: '/downloads', component: { template: '<div>Downloads</div>' } },
      { path: '/external', component: { template: '<div>Discover</div>' } },
      { path: '/type/:type', component: { template: '<div>Type</div>' } },
      { path: '/more', component: { template: '<div>More</div>' } },
      { path: '/:pathMatch(.*)*', component: { template: '<div>CatchAll</div>' } },
    ],
  })
  router.push(initialPath)
  return router
}

afterEach(() => {
  wrappers.forEach(w => w.unmount())
  wrappers.length = 0
  audioPlaybackStore.stop()
  vi.restoreAllMocks()
  localStorage.clear()
  sessionStorage.clear()
  document.body.innerHTML = ''
})

describe('TopBar /downloads navigation entrance', () => {
  const openOrganize = async (wrapper: ReturnType<typeof mount>) => {
    const organizeButton = wrapper.findAll('button').find(b => b.text().includes('更多'))
    expect(organizeButton).toBeTruthy()
    await organizeButton!.trigger('click')
    await nextTick()
  }

  it('provides a download task link under 系统与工具 accessible to all users', async () => {
    const router = createTestRouter('/')
    await router.isReady()

    const normalUser: User = { id: 2, username: 'member', is_admin: false, is_active: true, created_at: '' }
    const wrapper = mount(TopBar, {
      props: { user: normalUser },
      global: { plugins: [router] },
    })
    wrappers.push(wrapper)
    await openOrganize(wrapper)

    const downloadLink = wrapper.findAll('a').find(a => a.text().includes('下载任务'))
    expect(downloadLink).toBeTruthy()
    expect(downloadLink?.attributes('href')).toBe('/downloads')
    await downloadLink!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/downloads')
  })

  it('keeps admin-only organize entries hidden from non-admin users', async () => {
    const router = createTestRouter('/')
    await router.isReady()

    const normalUser: User = { id: 2, username: 'member', is_admin: false, is_active: true, created_at: '' }
    const wrapper = mount(TopBar, {
      props: { user: normalUser },
      global: { plugins: [router] },
    })
    wrappers.push(wrapper)
    await openOrganize(wrapper)

    const texts = wrapper.findAll('a').map(a => a.text())
    expect(texts).toContain('下载任务')
    expect(texts).not.toContain('设置')
    expect(texts).not.toContain('用户管理')
  })

  it('keeps the organize panel outside the scrolling navigation and closes it with Escape', async () => {
    const router = createTestRouter('/')
    await router.isReady()
    const wrapper = mount(TopBar, { props: { user: null }, global: { plugins: [router] } })
    wrappers.push(wrapper)
    await openOrganize(wrapper)
    const panel = wrapper.get('#organize-tools')
    expect(wrapper.get('nav[aria-label="主导航"]').element.contains(panel.element)).toBe(false)
    expect(panel.classes()).toContain('overflow-y-auto')
    expect(wrapper.get('button[aria-controls="organize-tools"]').attributes('aria-expanded')).toBe('true')
    await panel.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('#organize-tools').exists()).toBe(false)
    expect(wrapper.get('button[aria-controls="organize-tools"]').attributes('aria-expanded')).toBe('false')
  })
})

describe('MangaReader mobile webtoon mode and controls', () => {
  it('registers ordinary webtoon touch observers as passive so scrolling does not wait for them', () => {
    window.innerWidth = 390
    localStorage.setItem('he_manga_read_mode_mobile', 'webtoon')
    const listeners = vi.spyOn(HTMLElement.prototype, 'addEventListener')
    const wrapper = mount(MangaReader, { props: {
      media: sampleMangaMedia, currentPage: 0, totalPages: 3, pageDimensions: [],
      showControls: false, clickOnlyControls: true, progressText: '', progressPercent: 0,
    } })
    wrappers.push(wrapper)
    const viewport = wrapper.get('.he-webtoon-viewport').element
    const touches = listeners.mock.calls.filter(([type], index) =>
      listeners.mock.contexts[index] === viewport && type.startsWith('touch'))
    expect(touches.map(([type]) => type).sort()).toEqual(['touchcancel', 'touchend', 'touchmove', 'touchstart'])
    for (const [, , options] of touches) expect(options).toMatchObject({ passive: true })
  })

  it('correctly reports final page completion when scrolling to bottom on mobile web', async () => {
    localStorage.setItem('he_manga_read_mode', 'webtoon')
    localStorage.setItem('he_manga_read_mode_mobile', 'webtoon')
    window.innerWidth = 390
    let currentPageReported = 0
    const wrapper = mount(MangaReader, {
      props: {
        media: sampleMangaMedia,
        currentPage: 0,
        totalPages: 5,
        pageDimensions: [[800, 1200], [800, 1200], [800, 1200], [800, 1200], [800, 1200]],
        showControls: true,
        clickOnlyControls: true,
        progressText: '1 / 5',
        progressPercent: 20,
        'onUpdate:currentPage': (page: number) => { currentPageReported = page },
      },
    })
    wrappers.push(wrapper)
    await nextTick()

    const container = wrapper.find({ ref: 'webtoonContainerRef' }).element as HTMLElement
    expect(container).toBeTruthy()

    // Mock children offsetTop/offsetHeight for realistic layout
    Array.from(container.querySelectorAll('.he-reader-page')).forEach((child, idx) => {
      Object.defineProperty(child, 'offsetTop', { value: idx * 1200, configurable: true })
      Object.defineProperty(child, 'offsetHeight', { value: 1200, configurable: true })
    })

    // Wait past the initial programmatic scroll lockout (100ms)
    await new Promise(resolve => setTimeout(resolve, 150))

    // Mock container scroll dimensions representing scrolled all the way to bottom
    Object.defineProperty(container, 'scrollHeight', { value: 6000, configurable: true })
    Object.defineProperty(container, 'clientHeight', { value: 800, configurable: true })
    Object.defineProperty(container, 'scrollTop', { value: 5200, configurable: true }) // 5200 + 800 = 6000 (at bottom)

    // Trigger scroll handler
    container.dispatchEvent(new Event('scroll'))

    // Wait for requestAnimationFrame
    await new Promise(resolve => requestAnimationFrame(resolve))
    await nextTick()

    // Should report page 4 (the final page, 0-indexed) on mobile web
    expect(currentPageReported).toBe(4)
  })

  // Zoom gestures settle on animation frames before committing; these tests drive the frames.
  const animationFrames = () => {
    const queue = new Map<number, FrameRequestCallback>()
    let id = 0, time = 0
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { queue.set(++id, callback); return id })
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(handle => { queue.delete(handle) })
    return () => {
      for (let index = 0; index < 300 && queue.size; index++) {
        const batch = [...queue.values()]; queue.clear(); time += 16
        batch.forEach(callback => callback(time))
      }
    }
  }
  const renderedTree = (wrapper: ReturnType<typeof mount>) => (wrapper.vm as unknown as { $: { subTree: unknown } }).$.subTree
  const fingers = (...points: number[][]) => ({ touches: points.map(([clientX, clientY]) => ({ clientX, clientY })) })
  const lifted = (...points: number[][]) => ({ touches: [], changedTouches: points.map(([clientX, clientY]) => ({ clientX, clientY })) })
  const scaleOf = (element: HTMLElement) => Number(/scale\(([\d.]+)\)/.exec(element.style.transform)?.[1])
  // The shown page's carousel slot is the zoom surface.
  const currentSlot = (wrapper: ReturnType<typeof mount>) => wrapper.findAll('.he-pager-slot').find(slot => slot.find('.he-reader-canvas-page').exists())!
  const mountPaged = (mode: string, width = 390) => {
    window.innerWidth = width
    localStorage.setItem('he_manga_read_mode', mode)
    localStorage.setItem('he_manga_read_mode_mobile', mode)
    const wrapper = mount(MangaReader, { props: {
      media: sampleMangaMedia, currentPage: 0, totalPages: 3, pageDimensions: [[800, 1200], [800, 1200], [800, 1200]],
      showControls: false, clickOnlyControls: true, progressText: '1 / 3', progressPercent: 33,
    } })
    wrappers.push(wrapper)
    return wrapper
  }

  it.each(['single', 'double'])('keeps mobile %s zoom controls hidden until explicitly opened', async mode => {
    const flushFrames = animationFrames()
    const wrapper = mountPaged(mode)
    await nextTick()
    const zoomPill = wrapper.find('.he-manga-zoom')
    expect(zoomPill.exists()).toBe(true)
    expect(zoomPill.classes()).toContain('opacity-0')
    // Reach the hidden controls through the shown page's own pinch handlers.
    const slot = currentSlot(wrapper)
    await slot.trigger('touchstart', fingers([100, 100], [200, 100]))
    expect(wrapper.emitted('hideControls')).toEqual([[]])
    await slot.trigger('touchmove', fingers([50, 100], [250, 100]))
    await slot.trigger('touchend', lifted([50, 100], [250, 100]))
    flushFrames(); await nextTick()
    expect(zoomPill.classes()).toContain('opacity-0')
    expect(zoomPill.attributes('inert')).toBeDefined()
    await wrapper.setProps({ showControls: true })
    expect(zoomPill.classes()).toContain('opacity-100')
    expect(zoomPill.text()).toContain('200%')
    await zoomPill.get('button[aria-label="适应屏幕"]').trigger('click')
    flushFrames(); await nextTick()
    expect(zoomPill.text()).toContain('100%')
    await wrapper.setProps({ showControls: false })
    expect(zoomPill.attributes('inert')).toBeDefined()
  })

  it('retains visible zoom controls for a zoomed desktop viewport', async () => {
    const flushFrames = animationFrames()
    const wrapper = mountPaged('single', 1280)
    await nextTick()
    const slot = currentSlot(wrapper)
    await slot.trigger('touchstart', fingers([100, 100], [200, 100]))
    await slot.trigger('touchmove', fingers([50, 100], [250, 100]))
    await slot.trigger('touchend', lifted([50, 100], [250, 100]))
    flushFrames(); await nextTick()
    expect(wrapper.get('.he-manga-zoom').classes()).toContain('opacity-100')
    expect(wrapper.get('.he-manga-zoom').attributes('inert')).toBeUndefined()
    expect(wrapper.emitted('hideControls')).toBeUndefined()
  })

  it.each(['single', 'double'])('pinches the %s page without re-rendering the reader, and holds the pager still', async mode => {
    const flushFrames = animationFrames()
    const wrapper = mountPaged(mode)
    await nextTick()
    const slot = currentSlot(wrapper)
    const content = slot.get('.he-slide-content').element as HTMLElement
    await slot.trigger('touchstart', fingers([100, 100], [200, 100]))
    const tree = renderedTree(wrapper)
    for (const spread of [60, 80, 100]) { await slot.trigger('touchmove', fingers([150 - spread, 100], [150 + spread, 100])); flushFrames() }
    // Only the live transform changes; the page is laid out anew once the fingers lift.
    expect(scaleOf(content)).toBeCloseTo(2)
    expect(renderedTree(wrapper)).toBe(tree)
    expect((wrapper.get('.he-pager').element as HTMLElement).style.overflowX).toBe('hidden')
  })

  it('pinches the webtoon column without re-rendering every page on each move', async () => {
    const flushFrames = animationFrames()
    window.innerWidth = 390
    localStorage.setItem('he_manga_read_mode_mobile', 'webtoon')
    const wrapper = mount(MangaReader, { props: {
      media: sampleMangaMedia, currentPage: 0, totalPages: 3, pageDimensions: [[800, 1200], [800, 1200], [800, 1200]],
      showControls: false, clickOnlyControls: true, progressText: '', progressPercent: 0,
    } })
    wrappers.push(wrapper)
    await nextTick()
    const viewport = wrapper.get('.he-webtoon-viewport')
    const content = wrapper.get('.he-webtoon-content').element as HTMLElement
    await viewport.trigger('touchstart', fingers([100, 100], [200, 100]))
    const tree = renderedTree(wrapper)
    for (const spread of [60, 80, 100]) { await viewport.trigger('touchmove', fingers([150 - spread, 100], [150 + spread, 100])); flushFrames() }
    expect(scaleOf(content)).toBeCloseTo(2)
    expect(renderedTree(wrapper)).toBe(tree)
  })

  it.each(['single', 'webtoon'])('uses a touch double-tap to zoom %s reading and keeps a mouse double-click for fullscreen', async mode => {
    const flushFrames = animationFrames()
    const wrapper = mode === 'webtoon'
      ? (() => { localStorage.setItem('he_manga_read_mode_mobile', 'webtoon'); window.innerWidth = 390; const reader = mount(MangaReader, { props: { media: sampleMangaMedia, currentPage: 0, totalPages: 3, pageDimensions: [], showControls: false, clickOnlyControls: true, progressText: '', progressPercent: 0 } }); wrappers.push(reader); return reader })()
      : mountPaged(mode)
    await nextTick()
    const surface = mode === 'webtoon' ? wrapper.get('.he-webtoon-viewport') : currentSlot(wrapper)
    const content = (mode === 'webtoon' ? wrapper.get('.he-webtoon-content') : surface.get('.he-slide-content')).element as HTMLElement
    for (let tap = 0; tap < 2; tap++) {
      await surface.trigger('touchstart', fingers([195, 300]))
      await surface.trigger('touchend', lifted([195, 300]))
    }
    flushFrames()
    expect(content.style.getPropertyValue('--he-zoom')).toBe(mode === 'webtoon' ? '2' : '2.5')
    expect(wrapper.emitted('hideControls')).toEqual([[]])
    await surface.trigger('dblclick')
    expect(wrapper.emitted('viewerDoubleClick')).toBeUndefined()
    await surface.trigger('dblclick')
    expect(wrapper.emitted('viewerDoubleClick')).toEqual([[]])
  })

  it('turns pages with a native swipe, by spread in double mode, and reaches the next batch from the end slot', async () => {
    window.innerWidth = 390
    localStorage.setItem('he_image_read_mode_mobile', 'double')
    const pages = Array.from({ length: 5 }, (_, id) => ({ id: id + 300, title: `Image ${id}`, media_type: 'image' })) as Media[]
    const wrapper = mount(MangaReader, { props: {
      media: pages[0]!, imagePages: pages, hasNextBatch: true, currentPage: 0, totalPages: 5, pageDimensions: [],
      showControls: false, clickOnlyControls: true, progressText: '', progressPercent: 0,
    } })
    wrappers.push(wrapper)
    const pager = wrapper.get('.he-pager').element as HTMLElement
    Object.defineProperties(pager, { clientWidth: { value: 390, configurable: true }, clientHeight: { value: 800, configurable: true } })
    window.dispatchEvent(new Event('resize'))
    await wrapper.setProps({ progressText: 'measured' })
    const swipeTo = async (slot: number) => {
      pager.scrollLeft = slot * 390
      pager.dispatchEvent(new Event('scroll'))
      pager.dispatchEvent(new Event('scrollend'))
      await nextTick()
    }
    expect(wrapper.findAll('.he-reader-canvas-page').map(page => page.attributes('data-page'))).toEqual(['0', '1'])
    await swipeTo(1)
    expect(wrapper.emitted('update:currentPage')).toEqual([[2]])
    await wrapper.setProps({ currentPage: 2 })
    expect(wrapper.findAll('.he-reader-canvas-page').map(page => page.attributes('data-page'))).toEqual(['2', '3'])
    // Spreads [0,1] [2,3] [4]: slot 3 loads the next batch instead of a page.
    await swipeTo(3)
    expect(wrapper.emitted('boundary')).toEqual([[1]])
    expect(wrapper.text()).toContain('正在加载后面的图片')
  })
})

describe('AudioPlayer progress scrubbing on touch/pointer', () => {
  it('resets isScrubbing on pointerup even if change event does not fire', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: { tracks: [{ index: 1, title: 'Track 1', duration: 120, lyrics: null }] } })
    const wrapper = mount(AudioPlayer, {
      props: {
        media: sampleAudioMedia,
        coverUrl: '',
      },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await flushPromises()

    const audio = wrapper.find('audio').element as HTMLAudioElement
    Object.defineProperty(audio, 'duration', { value: 120, configurable: true })
    await wrapper.get('audio').trigger('loadedmetadata')
    const rangeInput = wrapper.find('input[type="range"]')
    expect(rangeInput.exists()).toBe(true)

    // User touches the scrub bar
    await rangeInput.trigger('pointerdown')

    // User drags to time 45s
    const inputEl = rangeInput.element as HTMLInputElement
    inputEl.value = '45'
    await rangeInput.trigger('input')

    // User lifts finger (pointerup), without triggering a change event
    await rangeInput.trigger('pointerup')
    await nextTick()

    // Range should reflect 45 and subsequent timeupdate should not be blocked
    expect(audio.currentTime).toBe(45)
    Object.defineProperty(audio, 'currentTime', { value: 60, configurable: true, writable: true })
    Object.defineProperty(audio, 'duration', { value: 120, configurable: true })
    audio.dispatchEvent(new Event('timeupdate'))
    await nextTick()

    expect(wrapper.text()).toContain('01:00')
  })
})

describe('GlobalAudioPlayer expansion and teardown', () => {
  it('expands and minimizes with focus restoration without changing browser history', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: sampleAudioMedia })
    const push = vi.spyOn(window.history, 'pushState')
    const replace = vi.spyOn(window.history, 'replaceState')
    const back = vi.spyOn(window.history, 'back')
    const initialHistory = { length: window.history.length, state: window.history.state, href: window.location.href }
    const wrapper = mount(GlobalAudioPlayer, {
      attachTo: document.body,
      global: { stubs: { AudioPlayer: true } },
    })
    wrappers.push(wrapper)
    audioPlaybackStore.open(sampleAudioMedia)
    await flushPromises()
    const minimize = document.querySelector<HTMLButtonElement>('[aria-label="收起播放器，继续播放"]')!
    expect(document.activeElement).toBe(minimize)
    minimize.click()
    await flushPromises()
    expect(audioPlaybackStore.state.expanded).toBe(false)
    const expand = document.querySelector<HTMLButtonElement>('[aria-label="展开音频播放器"]')!
    expect(document.activeElement).toBe(expand)
    expand.click()
    await flushPromises()
    expect(audioPlaybackStore.state.expanded).toBe(true)
    expect(document.activeElement).toBe(minimize)
    expect(push).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
    expect(back).not.toHaveBeenCalled()
    expect({ length: window.history.length, state: window.history.state, href: window.location.href }).toEqual(initialHistory)
  })

  it('stops playback on unmount without changing browser history', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: sampleAudioMedia })
    const push = vi.spyOn(window.history, 'pushState')
    const back = vi.spyOn(window.history, 'back')
    const stop = vi.spyOn(audioPlaybackStore, 'stop')
    const wrapper = mount(GlobalAudioPlayer, {
      attachTo: document.body,
      global: { stubs: { AudioPlayer: true } },
    })
    audioPlaybackStore.open(sampleAudioMedia)
    await flushPromises()
    stop.mockClear()
    wrapper.unmount()
    expect(stop).toHaveBeenCalledOnce()
    expect(audioPlaybackStore.state.media).toBeNull()
    expect(audioPlaybackStore.state.expanded).toBe(false)
    expect(document.querySelector('.he-audio-host')).toBeNull()
    expect(push).not.toHaveBeenCalled()
    expect(back).not.toHaveBeenCalled()
  })
})

describe('MobileNavigation active tab tap interaction', () => {
  it('dispatches he:scroll-top when tapping the currently active tab', async () => {
    const router = createTestRouter('/')
    await router.isReady()

    const scrollTopListener = vi.fn()
    window.addEventListener('he:scroll-top', scrollTopListener)

    const wrapper = mount(MobileNavigation, {
      global: { plugins: [router] },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await nextTick()

    // Click the active '媒体库' tab
    const libraryLink = wrapper.findAll('a').find(a => a.text().includes('媒体库'))
    expect(libraryLink).toBeTruthy()
    await libraryLink?.trigger('click')

    expect(scrollTopListener).toHaveBeenCalledOnce()
    window.removeEventListener('he:scroll-top', scrollTopListener)
  })

  it('keeps the saved library destination when tapping its active category tab', async () => {
    const router = createTestRouter('/type/video?search=kept&page=2')
    await router.isReady()

    const wrapper = mount(MobileNavigation, {
      global: { plugins: [router] },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await nextTick()

    const libraryLink = wrapper.findAll('a').find(a => a.text().includes('媒体库'))
    await libraryLink?.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/type/video?search=kept&page=2')
  })
})

describe('pinch sequences never become page swipes', () => {
  const touch = (points: number[][], changed: number[][] = [], type = 'touchend') => ({
    type,
    touches: points.map(([x, y]) => ({ clientX: x, clientY: y })),
    changedTouches: changed.map(([x, y]) => ({ clientX: x, clientY: y })),
    cancelable: true,
    preventDefault: vi.fn(),
  }) as unknown as TouchEvent

  it.each(['together', 'one finger then the other', 'canceled'])('suppresses navigation after a pinch shrinks to 1x and ends %s', ending => {
    const onSwipe = vi.fn()
    let zoom!: ReturnType<typeof useZoomScroller>
    const scroller = document.createElement('div'), content = document.createElement('div')
    scroller.append(content)
    const frames: FrameRequestCallback[] = []
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => frames.push(callback))
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
    wrappers.push(mount(defineComponent({
      setup() {
        zoom = useZoomScroller({ scroller: ref(scroller), content: ref(content), centered: true, onSwipe, applyScale: (element, scale) => element.style.setProperty('--he-zoom', String(scale)) })
        return () => h('div')
      },
    })))
    zoom.onTouchStart(touch([[100, 100], [300, 100]], [], 'touchstart'))
    zoom.onTouchMove(touch([[50, 100], [350, 100]], [], 'touchmove'))
    zoom.onTouchMove(touch([[190, 100], [210, 100]], [], 'touchmove'))
    if (ending === 'one finger then the other') {
      zoom.onTouchEnd(touch([[210, 100]], [[190, 100]]))
      zoom.onTouchMove(touch([[320, 100]], [], 'touchmove'))
      zoom.onTouchEnd(touch([], [[320, 100]]))
    } else if (ending === 'canceled') {
      zoom.onTouchEnd(touch([], [[320, 100]], 'touchcancel'))
      zoom.onTouchEnd(touch([], [[320, 100]]))
    } else {
      zoom.onTouchEnd(touch([], [[320, 100], [190, 100]]))
    }
    for (let frame = 0, time = 0; frame < 300 && frames.length; frame++) frames.splice(0).forEach(callback => callback(time += 16))
    expect(onSwipe).not.toHaveBeenCalled()
    // Rubber-banded below 1x while the fingers were down, then settled back at fit.
    expect(zoom.scale.value).toBe(1)
    expect(zoom.wasGesture()).toBe(true)
    zoom.onTouchStart(touch([[250, 100]], [], 'touchstart'))
    zoom.onTouchMove(touch([[180, 104]], [], 'touchmove'))
    zoom.onTouchEnd(touch([], [[100, 105]]))
    expect(onSwipe).toHaveBeenCalledExactlyOnceWith(1)
  })
})
