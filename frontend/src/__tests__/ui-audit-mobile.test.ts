import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'
import Sidebar from '../components/Sidebar.vue'
import MobileNavigation from '../components/MobileNavigation.vue'
import GlobalAudioPlayer from '../components/GlobalAudioPlayer.vue'
import AudioPlayer from '../components/media-detail/AudioPlayer.vue'
import MangaReader from '../components/media-detail/MangaReader.vue'
import { audioPlaybackStore } from '../stores/audioPlaybackStore'
import { useImageViewerZoom } from '../composables/useImageViewerZoom'
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

describe('Sidebar /downloads navigation entrance', () => {
  it('provides a download task link under 系统与工具 accessible to all users', async () => {
    const router = createTestRouter('/')
    await router.isReady()

    const normalUser: User = { id: 2, username: 'member', is_admin: false, is_active: true, created_at: '' }
    const wrapper = mount(Sidebar, {
      props: { collapsed: false, user: normalUser },
      global: { plugins: [router] },
    })
    wrappers.push(wrapper)

    const downloadLink = wrapper.findAll('a').find(a => a.text().includes('下载任务'))
    expect(downloadLink).toBeTruthy()
    expect(downloadLink?.attributes('href')).toBe('/downloads')
    await downloadLink!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/downloads')
  })

  it('highlights the download task navigation item when on /downloads route', async () => {
    const router = createTestRouter('/downloads')
    await router.isReady()

    const normalUser: User = { id: 2, username: 'member', is_admin: false, is_active: true, created_at: '' }
    const wrapper = mount(Sidebar, {
      props: { collapsed: false, user: normalUser },
      global: { plugins: [router] },
    })
    wrappers.push(wrapper)

    const downloadLink = wrapper.findAll('a').find(a => a.text().includes('下载任务'))
    expect(downloadLink?.attributes('aria-current')).toBe('page')
  })
})

describe('MangaReader mobile webtoon mode and controls', () => {
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

  it.each(['single', 'double'])('keeps mobile %s zoom controls hidden until explicitly opened', async mode => {
    window.innerWidth = 390
    localStorage.setItem('he_manga_read_mode', mode)
    localStorage.setItem('he_manga_read_mode_mobile', mode)

    const wrapper = mount(MangaReader, {
      props: {
        media: sampleMangaMedia,
        currentPage: 0,
        totalPages: 3,
        pageDimensions: [[800, 1200], [800, 1200], [800, 1200]],
        showControls: false, // controls hidden
        clickOnlyControls: true,
        progressText: '1 / 3',
        progressPercent: 33,
      },
    })
    wrappers.push(wrapper)
    await nextTick()

    const zoomPill = wrapper.find('.he-manga-zoom')
    expect(zoomPill.exists()).toBe(true)
    // Initially not zoomed and showControls=false -> opacity-0 pointer-events-none
    expect(zoomPill.classes()).toContain('opacity-0')

    // Reach the hidden controls through the actual canvas pinch handlers.
    const canvas = wrapper.find({ ref: 'imageContainerRef' })
    await canvas.trigger('touchstart', { touches: [{ clientX: 100, clientY: 100 }, { clientX: 200, clientY: 100 }] })
    expect(wrapper.emitted('hideControls')).toEqual([[]])
    await canvas.trigger('touchmove', { touches: [{ clientX: 50, clientY: 100 }, { clientX: 250, clientY: 100 }] })
    await canvas.trigger('touchend', { touches: [], changedTouches: [{ clientX: 50, clientY: 100 }, { clientX: 250, clientY: 100 }] })
    expect(zoomPill.classes()).toContain('opacity-0')
    expect(zoomPill.attributes('inert')).toBeDefined()
    await wrapper.setProps({ showControls: true })
    expect(zoomPill.classes()).toContain('opacity-100')
    expect(zoomPill.text()).toContain('200%')
    await zoomPill.get('button[aria-label="适应屏幕"]').trigger('click')
    expect(zoomPill.text()).toContain('100%')
    await wrapper.setProps({ showControls: false })
    expect(zoomPill.attributes('inert')).toBeDefined()
  })

  it('retains visible zoom controls for a zoomed desktop viewport', async () => {
    window.innerWidth = 1280
    localStorage.setItem('he_manga_read_mode', 'single')
    const wrapper = mount(MangaReader, { props: {
      media: sampleMangaMedia, currentPage: 0, totalPages: 3, pageDimensions: [],
      showControls: false, clickOnlyControls: true, progressText: '', progressPercent: 0,
    } })
    wrappers.push(wrapper)
    const canvas = wrapper.find({ ref: 'imageContainerRef' })
    await canvas.trigger('touchstart', { touches: [{ clientX: 100, clientY: 100 }, { clientX: 200, clientY: 100 }] })
    await canvas.trigger('touchmove', { touches: [{ clientX: 50, clientY: 100 }, { clientX: 250, clientY: 100 }] })
    expect(wrapper.get('.he-manga-zoom').classes()).toContain('opacity-100')
    expect(wrapper.get('.he-manga-zoom').attributes('inert')).toBeUndefined()
    expect(wrapper.emitted('hideControls')).toBeUndefined()
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

describe('useImageViewerZoom touch gestures', () => {
  it('transitions from 2-finger pinch to 1-finger pan smoothly without freezing', () => {
    const container = document.createElement('div')
    Object.defineProperty(container, 'getBoundingClientRect', {
      value: () => ({ width: 400, height: 600, top: 0, left: 0, right: 400, bottom: 600 } as DOMRect),
    })

    let zoom!: ReturnType<typeof useImageViewerZoom>
    const wrapper = mount(defineComponent({
      setup() {
        zoom = useImageViewerZoom(ref(container))
        return () => h('div')
      },
    }))
    wrappers.push(wrapper)

    const makeTouch = (points: number[][], changed: number[][] = []) => ({
      touches: points.map(([x, y]) => ({ clientX: x, clientY: y })),
      changedTouches: changed.map(([x, y]) => ({ clientX: x, clientY: y })),
      cancelable: true,
      preventDefault: vi.fn(),
    }) as unknown as TouchEvent

    // 2-finger pinch starts
    zoom.onTouchStart(makeTouch([[100, 100], [200, 100]]))
    zoom.onTouchMove(makeTouch([[50, 100], [250, 100]]))
    expect(zoom.scale.value).toBe(2)

    // User lifts 1 finger, leaving 1 finger on screen
    zoom.onTouchEnd(makeTouch([[250, 100]], [[50, 100]]))

    // Moving the remaining single finger should pan the zoomed image smoothly
    const beforePan = zoom.translateX.value
    zoom.onTouchMove(makeTouch([[280, 100]]))
    expect(zoom.translateX.value).toBeGreaterThan(beforePan)
    expect(zoom.isPanning.value).toBe(true)

    // resetZoom resets all states cleanly
    zoom.resetZoom()
    expect(zoom.scale.value).toBe(1)
    expect(zoom.translateX.value).toBe(0)
    expect(zoom.wasTouchGesture()).toBe(false)
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
    let zoom!: ReturnType<typeof useImageViewerZoom>
    wrappers.push(mount(defineComponent({
      setup() { zoom = useImageViewerZoom(ref(null), { onSwipe }); return () => h('div') },
    })))
    zoom.onTouchStart(touch([[100, 100], [300, 100]]))
    zoom.onTouchMove(touch([[50, 100], [350, 100]]))
    expect(zoom.scale.value).toBe(1.5)
    zoom.onTouchMove(touch([[190, 100], [210, 100]]))
    expect(zoom.scale.value).toBe(1)
    if (ending === 'one finger then the other') {
      zoom.onTouchEnd(touch([[210, 100]], [[190, 100]]))
      zoom.onTouchMove(touch([[320, 100]]))
      zoom.onTouchEnd(touch([], [[320, 100]]))
    } else if (ending === 'canceled') {
      zoom.onTouchEnd(touch([], [[320, 100]], 'touchcancel'))
      zoom.onTouchEnd(touch([], [[320, 100]]))
    } else {
      zoom.onTouchEnd(touch([], [[320, 100], [190, 100]]))
    }
    expect(onSwipe).not.toHaveBeenCalled()
    expect(zoom.wasTouchGesture()).toBe(true)
    zoom.onTouchStart(touch([[250, 100]]))
    zoom.onTouchEnd(touch([], [[100, 105]]))
    expect(onSwipe).toHaveBeenCalledExactlyOnceWith(1)
  })
})
