import { afterEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'
import HomeView from '../views/HomeView.vue'
import { authState } from '../auth'
import PaginationControl from '../components/PaginationControl.vue'
import MediaCard from '../components/MediaCard.vue'
import type { Media } from '../types'

describe('ui-audit-web: PaginationControl', () => {
  it('correctly calculates rangeStart and rangeEnd without exceeding boundaries', () => {
    const wrapper = mount(PaginationControl, {
      props: {
        page: 1,
        pageCount: 5,
        totalItems: 42,
        pageSize: 10,
      },
    })

    // Normal page 1
    const summary = wrapper.find('.media-pagination__summary')
    expect(summary.text()).toContain('1–10')
    expect(summary.text()).toContain('共 42 项')
  })

  it('bounds rangeStart and rangeEnd when page exceeds pageCount or items are zero', async () => {
    const wrapper = mount(PaginationControl, {
      props: {
        page: 3,
        pageCount: 2,
        totalItems: 15,
        pageSize: 10,
      },
    })

    // Page 3 with only 15 items should not show 21–15
    const summary = wrapper.find('.media-pagination__summary')
    expect(summary.text()).toContain('15–15')

    // Zero items
    await wrapper.setProps({ totalItems: 0, page: 1, pageCount: 1 })
    expect(wrapper.find('.media-pagination__summary').text()).toContain('共 0 项')
  })

  it('preserves focus on navigation buttons and only returns focus when picker panel was open', async () => {
    const wrapper = mount(PaginationControl, {
      props: {
        page: 2,
        pageCount: 5,
        totalItems: 50,
        pageSize: 10,
      },
      attachTo: document.body,
    })

    const nextBtn = wrapper.find('button[aria-label="下一页"]')
    await nextBtn.trigger('click')
    expect(wrapper.emitted('change')?.[0]).toEqual([3])

    // Trigger should NOT have been focused because picker was closed
    const trigger = wrapper.find('.media-page-picker__trigger')
    expect(document.activeElement).not.toBe(trigger.element)

    // Now open the picker and choose page
    await trigger.trigger('click')
    expect(wrapper.find('.media-page-picker__panel').exists()).toBe(true)

    const pageBtn = wrapper.find('button[data-page="4"]')
    await pageBtn.trigger('click')
    expect(wrapper.emitted('change')?.[1]).toEqual([4])
    await nextTick()
    // When chosen from open picker, focus returns to trigger
    expect(document.activeElement).toBe(trigger.element)

    wrapper.unmount()
  })


})

describe('ui-audit-web: MediaCard robustness', () => {
  const baseMedia: Media = {
    id: 1,
    title: 'Test Media',
    relative_path: 'test.mp4',
    media_type: 'video',
    extension: '.mp4',
    file_size: 1048576, // 1 MB
    cover_path: '/covers/1.jpg',
    duration: 125,
    width: 1920,
    height: 1080,
    page_count: null,
    rating: 4,
    favorite: false,
    view_status: 'unviewed',
    progress: 0,
    last_opened_at: null,
    source_url: null,
    source_site: null,
    is_missing: false,
    missing_since: null,
    created_at: '2026-01-01T00:00:00Z',
    tags: [],
  }

  it('handles null/missing extension gracefully', () => {
    const mediaWithoutExt = { ...baseMedia, extension: '' } as any
    const wrapper = mount(MediaCard, {
      props: { media: mediaWithoutExt },
    })
    expect(wrapper.text()).toContain('DIR')
  })

  it('handles 0 or negative file sizes without producing NaN in formatSize', () => {
    const zeroMedia = { ...baseMedia, file_size: 0 }
    const wrapper = mount(MediaCard, {
      props: { media: zeroMedia },
    })
    expect(wrapper.text()).toContain('本地目录')

    const negativeMedia = { ...baseMedia, file_size: -100 }
    const wrapper2 = mount(MediaCard, {
      props: { media: negativeMedia },
    })
    expect(wrapper2.text()).not.toContain('NaN')
  })

  it('handles manga with zero or negative page counts safely', () => {
    const mangaMedia: Media = {
      ...baseMedia,
      media_type: 'manga',
      page_count: 0,
      progress: 5,
      view_status: 'viewing',
    }
    const wrapper = mount(MediaCard, {
      props: { media: mangaMedia },
    })
    expect(wrapper.text()).not.toContain('NaN')
  })
})


describe('media library route interactions', () => {
  let wrapper: ReturnType<typeof mount> | undefined
  afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks(); localStorage.removeItem('he_continue_collapsed') })
  const setup = async (url: string, continueCount = 0) => {
    authState.user = { id: 1, username: 'reader', is_admin: false, is_active: true, created_at: '' }
    const media = Array.from({ length: 36 }, (_, index) => ({
      id: index + 1, title: 'Sample', relative_path: 'sample.mp4', media_type: 'video',
      extension: '.mp4', file_size: 1000, cover_path: null, duration: 60, width: 640,
      height: 360, page_count: null, rating: 0, favorite: false, view_status: 'unviewed',
      progress: 0, last_opened_at: null, source_url: null, source_site: null,
      is_missing: false, missing_since: null, created_at: '', tags: [],
    }))
    const get = vi.spyOn(axios, 'get').mockImplementation(async (url, config) => ({
      data: String(url).endsWith('/tags') ? [] : config?.params?.sort === 'opened'
        ? media.slice(0, continueCount).map(item => ({ ...item, last_opened_at: '2026-01-01T00:00:00Z' })) : media,
      headers: { 'x-total-count': '100' },
    }))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
    await router.push(url)
    wrapper = mount(HomeView, { global: { plugins: [router], stubs: { MediaDetail: true } } })
    await flushPromises()
    return { router, get }
  }
  it('clears all filter query parameters while preserving the selected view', async () => {
    const { router } = await setup('/?favorite=true&search=keep&tag=art&source=local&sort=rating&page=2&view=list')
    const clear = wrapper!.findAll('button').find(button => button.text().includes('清除筛选'))
    expect(clear).toBeDefined()
    await clear!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ view: 'list' })
  })
  it('requests the new page once and preserves its URL for browser navigation', async () => {
    const { router, get } = await setup('/?view=list')
    get.mockClear()
    await wrapper!.get('button[aria-label="下一页"]').trigger('click')
    await flushPromises()
    const pages = get.mock.calls.filter(([url]) => String(url).endsWith('/media'))
    expect(pages).toHaveLength(1)
    expect(pages[0]![1]?.params).toMatchObject({ offset: 36 })
    expect(router.currentRoute.value.query).toEqual({ view: 'list', page: '2' })
  })
  it('keeps the previous media visible but inactive while the new category loads', async () => {
    const { get } = await setup('/?view=poster')
    const originalGet = get.getMockImplementation()!
    let finish!: (response: any) => void
    const pending = new Promise<any>(resolve => { finish = resolve })
    get.mockImplementation((url, config) => String(url).endsWith('/media') && config?.params?.sort !== 'opened'
      ? pending : originalGet(url, config))

    vi.useFakeTimers()
    try {
      await wrapper!.setProps({ mediaType: 'manga' })
      expect(wrapper!.find('[data-media-id="1"]').exists()).toBe(true)
      expect(wrapper!.get('[role="status"]').text()).toBe('')
      expect(wrapper!.get('[data-media-id="1"]').element.closest('[inert]')).not.toBeNull()
      await vi.advanceTimersByTimeAsync(300)
      expect(wrapper!.get('.he-page-header [role="status"]').text()).toContain('正在加载媒体')

      finish({ data: [], headers: { 'x-total-count': '0' } })
      await flushPromises()
      expect(wrapper!.get('[role="status"]').text()).toBe('')
      expect(wrapper!.find('[data-media-id="1"]').exists()).toBe(false)
      expect(wrapper!.text()).toContain('没有找到匹配的媒体')

      get.mockImplementation(originalGet)
      await wrapper!.setProps({ mediaType: 'video' })
      await flushPromises()
      await vi.advanceTimersByTimeAsync(300)
      expect(wrapper!.get('[role="status"]').text()).toBe('')
    } finally { vi.useRealTimers() }
  })
  it('switches the grid layout and continue content together without reshaping old covers', async () => {
    const { get } = await setup('/?view=poster', 2)
    const originalGet = get.getMockImplementation()!
    const result = await originalGet('/media', { params: {} })
    let finishList!: (response: any) => void
    let finishContinue!: (response: any) => void
    const list = new Promise<any>(resolve => { finishList = resolve })
    const recent = new Promise<any>(resolve => { finishContinue = resolve })
    get.mockImplementation((url, config) => String(url).endsWith('/media')
      ? config?.params?.sort === 'opened' ? recent : list : originalGet(url, config))
    const oldFrame = wrapper!.get('.he-media-card__frame').attributes('style')
    await wrapper!.setProps({ mediaType: 'video' })
    expect(wrapper!.get('.he-media-card__frame').attributes('style')).toBe(oldFrame)
    expect(wrapper!.find('button[aria-label="下一页"]').exists()).toBe(true)
    expect(wrapper!.get('button[aria-label="下一页"]').attributes('disabled')).toBeDefined()
    finishList(result)
    await flushPromises()
    expect(wrapper!.get('.he-media-card__frame').attributes('style')).toBe(oldFrame)
    expect(wrapper!.find('section[aria-label="今晚继续"]').exists()).toBe(true)
    finishContinue({ data: [], headers: {} })
    await flushPromises()
    expect(wrapper!.get('.he-media-card__frame').attributes('style')).toContain('16 / 9')
    expect(wrapper!.find('section[aria-label="今晚继续"]').exists()).toBe(false)
  })
  it('opens the collapsed continue list before scrolling to it', async () => {
    localStorage.setItem('he_continue_collapsed', 'true')
    await setup('/', 2)
    const section = wrapper!.get('section[aria-label="继续观看"]')
    const scroll = vi.fn()
    section.element.scrollIntoView = scroll
    expect(wrapper!.get('button[title="展开继续观看"]').attributes('aria-expanded')).toBe('false')
    const button = wrapper!.findAll('button').find(item => item.text().includes('看看其他继续项'))!
    await button.trigger('click')
    await nextTick()
    expect(wrapper!.get('button[title="收起继续观看"]').attributes('aria-expanded')).toBe('true')
    expect(scroll).toHaveBeenCalledOnce()
  })
  it('does not offer other continue items when there is only one', async () => {
    await setup('/', 1)
    expect(wrapper!.text()).not.toContain('看看其他继续项')
  })
  it('preserves the continue row and its scroll position across repeated toggles', async () => {
    await setup('/', 8)
    const row = wrapper!.get('section[aria-label="继续观看"] [class*="overflow-x-auto"]')
    const element = row.element as HTMLElement
    element.scrollLeft = 180
    for (let i = 0; i < 4; i++) {
      const toggle = wrapper!.get('section[aria-label="继续观看"] button[aria-expanded]')
      const wasExpanded = toggle.attributes('aria-expanded') === 'true'
      await toggle.trigger('click')
      expect(element.closest('[inert]') !== null).toBe(wasExpanded)
      expect(row.element).toBe(element)
      expect(element.scrollLeft).toBe(180)
    }
  })
  it('drags the continue row with a mouse without opening a media item', async () => {
    const { get } = await setup('/', 8)
    const row = wrapper!.get('section[aria-label="继续观看"] [class*="overflow-x-auto"]')
    const element = row.element as HTMLElement
    element.setPointerCapture = vi.fn()
    const item = row.get('button[aria-label^="打开媒体"]')
    await item.trigger('pointerdown', { pointerType: 'mouse', pointerId: 1, button: 0, clientX: 200 })
    await row.trigger('pointermove', { pointerType: 'mouse', pointerId: 1, clientX: 100 })
    expect(element.scrollLeft).toBe(100)
    expect(row.classes()).toContain('cursor-grabbing')
    await row.trigger('pointerup', { pointerType: 'mouse', pointerId: 1, clientX: 100 })
    await item.trigger('click', { detail: 1 })
    expect(get.mock.calls.some(([url]) => String(url) === '/media/1')).toBe(false)
  })
  it('uses whole grid rows and keeps pagination contiguous after a resize', async () => {
    localStorage.setItem('he_media_view_all', 'poster')
    let columns = 7
    let resize!: ResizeObserverCallback
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: ResizeObserverCallback) { resize = callback }
      observe() {}
      disconnect() {}
    })
    const originalStyle = window.getComputedStyle.bind(window)
    vi.spyOn(window, 'getComputedStyle').mockImplementation(element => {
      const style = originalStyle(element)
      return element.hasAttribute('data-media-grid')
        ? new Proxy(style, { get: (target, key) => key === 'gridTemplateColumns' ? Array(columns).fill('180px').join(' ') : Reflect.get(target, key, target) })
        : style
    })
    try {
      const { get } = await setup('/')
      expect(get).toHaveBeenCalledWith('/media', expect.objectContaining({ params: expect.objectContaining({ limit: 35, offset: 0 }) }))
      await wrapper!.get('button[aria-label="下一页"]').trigger('click')
      await flushPromises()
      expect(get).toHaveBeenCalledWith('/media', expect.objectContaining({ params: expect.objectContaining({ limit: 35, offset: 35 }) }))
      columns = 8
      vi.useFakeTimers()
      resize([], {} as ResizeObserver)
      await vi.advanceTimersByTimeAsync(150)
      await flushPromises()
      expect(get).toHaveBeenCalledWith('/media', expect.objectContaining({ params: expect.objectContaining({ limit: 32, offset: 32 }) }))
      await wrapper!.get('button[aria-label="下一页"]').trigger('click')
      await flushPromises()
      expect(get).toHaveBeenCalledWith('/media', expect.objectContaining({ params: expect.objectContaining({ limit: 32, offset: 64 }) }))
    } finally {
      vi.useRealTimers()
      vi.unstubAllGlobals()
    }
  })
})
