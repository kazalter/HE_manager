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
    buffer.requestWindow(['20','21','22'])
    expect(buffer.states.has('3')).toBe(false)
    await ControlledImage.instances[0]!.onload!()
    expect(ControlledImage.instances[0]!.decode).toHaveBeenCalledOnce()
    expect(buffer.states.get('0')?.status).toBe('ready')
    expect(ControlledImage.instances[3]!.src).toBe('20')
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
    buffer.clear(); buffer.requestWindow(['new'])
    await ControlledImage.instances[1]!.onload!()
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
