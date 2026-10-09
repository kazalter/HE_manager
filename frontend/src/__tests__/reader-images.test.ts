import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import MangaReader from '../components/media-detail/MangaReader.vue'
import { useReaderImageBuffer } from '../composables/useReaderImageBuffer'
import { useMediaOverlayControls } from '../composables/useMediaOverlayControls'
import type { Media } from '../types'

class ControlledImage {
  static instances: ControlledImage[] = []
  src = ''
  decoding = ''
  naturalWidth = 800
  naturalHeight = 1200
  onload: (() => Promise<void>) | null = null
  onerror: (() => void) | null = null
  decode = vi.fn().mockResolvedValue(undefined)
  constructor() { ControlledImage.instances.push(this) }
}
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => {
  wrappers.forEach(wrapper => wrapper.unmount()); wrappers.length = 0
  vi.unstubAllGlobals(); vi.useRealTimers(); localStorage.clear()
  ControlledImage.instances = []
})

describe('reader images and controls', () => {
  it('hides and restores non-fullscreen image controls on deliberate clicks', async () => {
    vi.useFakeTimers()
    let controls!: ReturnType<typeof useMediaOverlayControls>
    wrappers.push(mount(defineComponent({ setup() {
      controls = useMediaOverlayControls(computed(() => false), computed(() => true))
      return {}
    }, template: '<div />' })))
    expect(controls.isFullscreen.value).toBe(false)
    controls.handleViewerClick(); vi.advanceTimersByTime(250)
    expect(controls.showControls.value).toBe(false)
    window.dispatchEvent(new MouseEvent('mousemove'))
    expect(controls.showControls.value).toBe(false)
    controls.handleViewerClick(); vi.advanceTimersByTime(250)
    expect(controls.showControls.value).toBe(true)
  })

  it('limits concurrent work, decodes before ready, and prioritizes a distant jump', async () => {
    vi.stubGlobal('Image', ControlledImage)
    const buffer = useReaderImageBuffer()
    buffer.requestWindow(['0','1','2','3','4','5','6'])
    expect(ControlledImage.instances.map(img => img.src)).toEqual(['0','1','2'])
    expect(buffer.states.get('0')?.status).toBe('loading')
    const obsoleteLoad = ControlledImage.instances[0]!.onload!
    buffer.requestWindow(['20','21','22'])
    expect(buffer.states.has('3')).toBe(false)
    expect(ControlledImage.instances.slice(3).map(img => img.src)).toEqual(['20','21','22'])
    await obsoleteLoad()
    expect(buffer.states.has('0')).toBe(false)
    await ControlledImage.instances[3]!.onload!()
    expect(ControlledImage.instances[3]!.decode).toHaveBeenCalledOnce()
    expect(buffer.states.get('20')?.status).toBe('ready')
    buffer.dispose()
  })

  it('supports retry and ignores old completions after changing books or closing', async () => {
    vi.stubGlobal('Image', ControlledImage)
    const buffer = useReaderImageBuffer()
    buffer.requestWindow(['broken'])
    ControlledImage.instances[0]!.onerror!()
    expect(buffer.states.get('broken')?.status).toBe('error')
    buffer.retry('broken')
    expect(ControlledImage.instances[1]!.src).toBe('broken')
    const obsoleteLoad = ControlledImage.instances[1]!.onload!
    buffer.clear(); buffer.requestWindow(['new'])
    await obsoleteLoad()
    expect(buffer.states.has('broken')).toBe(false)
    await ControlledImage.instances[2]!.onload!()
    expect(buffer.states.get('new')?.width).toBe(800)
    buffer.dispose()
  })

  it('uses image streams, offers three modes, advances spreads, and omits all thumbnails', async () => {
    vi.stubGlobal('Image', ControlledImage)
    const images = Array.from({ length: 20 }, (_, id) => ({ id: id + 100, title: `Image ${id}`, media_type: 'image' })) as Media[]
    const wrapper = mount(MangaReader, { props: {
      media: images[0]!, imagePages: images, currentPage: 0, totalPages: 20,
      pageDimensions: [], showControls: true, clickOnlyControls: true,
      progressText: '1 / 20', progressPercent: 5,
    } })
    wrappers.push(wrapper)
    expect(wrapper.find('.he-manga-strip').exists()).toBe(false)
    expect(wrapper.find('[title="展开底部预览长条"]').exists()).toBe(false)
    expect(ControlledImage.instances.map(img => img.src).every(url => url.includes('/stream/'))).toBe(true)
    expect(ControlledImage.instances.length).toBe(3)
    await wrapper.get('[title="双页跨页模式"]').trigger('click')
    await wrapper.get('[title="下一页"]').trigger('click')
    expect(wrapper.emitted('update:currentPage')?.at(-1)).toEqual([2])
    await ControlledImage.instances[0]!.onload!()
    await ControlledImage.instances[1]!.onload!()
    await flushPromises()
    expect(wrapper.findAll('img').length).toBe(2)
    await wrapper.get('[title="连续卷轴模式 (条漫)"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.he-reader-page').length).toBe(20)
    expect(wrapper.get('#webtoon-page-0').attributes('style')).toContain('aspect-ratio')
    await wrapper.setProps({ showControls: false })
    expect(wrapper.get('.he-manga-controls').attributes('inert')).toBeDefined()
    expect(wrapper.find('.he-reader-page .font-mono').exists()).toBe(false)
  })
})


const mountCanvasReader = (imageLibrary = true) => {
  vi.stubGlobal('Image', ControlledImage)
  const pages = Array.from({ length: 9 }, (_, id) => ({ id: id + 100, title: `Image ${id}`, media_type: 'image' })) as Media[]
  const wrapper = mount(MangaReader, { props: {
    media: pages[0]!, imagePages: imageLibrary ? pages : undefined,
    currentPage: 0, totalPages: pages.length, pageDimensions: [],
    showControls: false, clickOnlyControls: true, progressText: '1 / 9', progressPercent: 11,
  } })
  wrappers.push(wrapper)
  return wrapper
}

const finishImage = async (index: number) => {
  await ControlledImage.instances[index]!.onload!()
  await flushPromises()
}

describe('canvas reader loading feedback', () => {
  it('replaces the old image with loading feedback until the next image has decoded', async () => {
    const wrapper = mountCanvasReader()
    expect(wrapper.text()).toContain('正在加载第 1 张')
    expect(wrapper.findAll('img')).toHaveLength(0)
    await finishImage(0)
    const first = wrapper.get('.he-reader-canvas-page img').element
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    await wrapper.setProps({ currentPage: 1 })
    expect(wrapper.text()).toContain('正在加载第 2 张')
    expect(wrapper.get('.he-reader-canvas-page').attributes('aria-busy')).toBe('true')
    expect(wrapper.findAll('img')).toHaveLength(0)
    let decoded!: () => void
    ControlledImage.instances[1]!.decode.mockImplementation(() => new Promise<void>(resolve => { decoded = resolve }))
    const loading = ControlledImage.instances[1]!.onload!()
    await flushPromises()
    expect(wrapper.text()).toContain('正在加载第 2 张')
    decoded(); await loading; await flushPromises()
    expect(wrapper.get('.he-reader-canvas-page img').attributes('src')).toContain('/stream/101')
    expect(wrapper.get('.he-reader-canvas-page img').element).not.toBe(first)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('keeps feedback on the requested page when a skipped image finishes late', async () => {
    const wrapper = mountCanvasReader()
    await wrapper.setProps({ currentPage: 1 })
    await wrapper.setProps({ currentPage: 2 })
    await finishImage(0)
    await finishImage(1)
    expect(wrapper.text()).toContain('正在加载第 3 张')
    expect(wrapper.findAll('img')).toHaveLength(0)
    await finishImage(2)
    expect(wrapper.get('.he-reader-canvas-page img').attributes('src')).toContain('/stream/102')
  })

  it('shows cached decoded pages immediately when navigating back', async () => {
    const wrapper = mountCanvasReader()
    await finishImage(0); await finishImage(1)
    await wrapper.setProps({ currentPage: 1 })
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    await wrapper.setProps({ currentPage: 0 })
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.get('.he-reader-canvas-page img').attributes('src')).toContain('/stream/100')
  })

  it('shows failures and retries the affected manga page without navigating or toggling controls', async () => {
    const wrapper = mountCanvasReader(false)
    ControlledImage.instances[0]!.onerror!()
    await flushPromises()
    expect(wrapper.text()).toContain('第 1 页加载失败')
    const retry = wrapper.get('.he-reader-canvas-page button')
    await retry.trigger('click')
    expect(wrapper.text()).toContain('正在加载第 1 页')
    expect(wrapper.emitted('viewerClick')).toBeUndefined()
    expect(wrapper.emitted('update:currentPage')).toBeUndefined()
    const retried = [...ControlledImage.instances].reverse().find(img => img.src.includes('/manga/100/page/0'))!
    expect(retried).not.toBe(ControlledImage.instances[0])
    await retried.onload!(); await flushPromises()
    expect(wrapper.find('.he-reader-canvas-page [role="status"]').exists()).toBe(false)
    expect(wrapper.get('.he-reader-canvas-page img').attributes('src')).toContain('/manga/100/page/0')
  })

  it('loads each half of a spread independently and preserves RTL order and the final single page', async () => {
    const wrapper = mountCanvasReader()
    await wrapper.get('[title="双页跨页模式"]').trigger('click')
    await finishImage(0)
    expect(wrapper.findAll('.he-reader-canvas-page img')).toHaveLength(1)
    expect(wrapper.text()).toContain('正在加载第 2 张')
    await wrapper.get('[title="普通从左往右翻 (LTR)"]').trigger('click')
    expect(wrapper.findAll('.he-reader-canvas-page').map(page => page.attributes('aria-label'))).toEqual(['第 2 张', '第 1 张'])
    await wrapper.setProps({ currentPage: 8 })
    expect(wrapper.findAll('.he-reader-canvas-page')).toHaveLength(1)
    expect(wrapper.text()).toContain('正在加载第 9 张')
  })
})


it('starts a visible retry immediately when all three slots are occupied by speculative images', async () => {
  vi.stubGlobal('Image', ControlledImage)
  const buffer = useReaderImageBuffer()
  buffer.requestWindow(['current', 'next', 'later', 'speculation'])
  ControlledImage.instances[0]!.onerror!()
  expect(buffer.states.get('current')?.status).toBe('error')
  const lateSpeculation = ControlledImage.instances[3]!.onload!
  buffer.retry('current')
  expect(ControlledImage.instances[4]?.src).toBe('current')
  expect(buffer.states.get('current')?.status).toBe('loading')
  await lateSpeculation()
  expect(buffer.states.get('speculation')?.status).toBe('queued')
  await ControlledImage.instances[4]!.onload!()
  expect(buffer.states.get('current')?.status).toBe('ready')
  buffer.dispose()
})

it('prioritizes both visible pages over a stalled speculative request when advancing a spread', () => {
  vi.stubGlobal('Image', ControlledImage)
  const buffer = useReaderImageBuffer()
  buffer.requestWindow(['0', '1', '2', '3', '4'], 2)
  buffer.requestWindow(['2', '3', '4', '1', '0'], 2)
  expect(ControlledImage.instances[3]?.src).toBe('3')
  expect(buffer.states.get('2')?.status).toBe('loading')
  expect(buffer.states.get('3')?.status).toBe('loading')
  expect([...buffer.states.values()].filter(state => state.status === 'loading')).toHaveLength(3)
  buffer.dispose()
})
