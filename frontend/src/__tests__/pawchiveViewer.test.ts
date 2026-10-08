import { nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PawchiveMediaViewer from '../components/external/pawchive/PawchiveMediaViewer.vue'
import type { PawchiveAttachment, PawchivePost } from '../types/pawchive'

const attachment: PawchiveAttachment = {
  attachment_key: 'image', original_index: 0, filename: 'image.jpg',
  media_type: 'image', mime_type: 'image/jpeg', stream_ref: 'image-ref',
  preview_ref: 'preview-ref', availability: 'playable',
}
const post: PawchivePost = {
  post_key: 'post', service: 'fanbox', creator_id: 'creator', post_id: 'post',
  title: 'Example', creator_name: 'Creator', source_url: 'https://pawchive.pw',
  published_at: null, reported_attachment_count: 1, playable_count: 1,
  preview_ref: 'preview-ref', tags: [], attachments: [attachment],
}

const imageResponse = () => new Response(new Blob(['jpeg'], { type: 'image/jpeg' }), {
  status: 200, headers: { 'content-type': 'image/jpeg', 'content-length': '4' },
})

describe('Pawchive fullscreen viewer', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => imageResponse()))
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:image'), revokeObjectURL: vi.fn() }))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it.each(['missing', 'rejected'])('uses immersive image mode when fullscreen is %s', async (failure) => {
    const wrapper = mount(PawchiveMediaViewer, {
      attachTo: document.body,
      props: {
        post, attachment, attachments: [attachment], attachmentIndex: 0, attachmentTotal: 1,
        scopeLabel: 'Example', busy: false, error: '', hasPrevious: false, ended: false,
        autoplay: false, interval: 5, downloadBusy: false, downloadMessage: '', downloadError: false,
      },
    })
    Object.defineProperty(wrapper.element, 'requestFullscreen', {
      configurable: true,
      value: failure === 'missing' ? undefined : vi.fn().mockRejectedValue(new Error('unsupported')),
    })
    try {
      await flushPromises()
      await wrapper.get('button[aria-label="进入全屏"]').trigger('click')
      await nextTick()
      expect(wrapper.find('button[aria-label="退出全屏"]').exists()).toBe(true)
      expect(wrapper.get('header').classes()).toContain('absolute')
      expect(wrapper.get('footer').classes()).toContain('absolute')
      expect(wrapper.emitted('playbackError')).toBeUndefined()

      await wrapper.get('img[alt="image.jpg"]').trigger('click')
      await nextTick()
      expect(wrapper.get('header').classes()).toContain('opacity-0')
      await wrapper.get('img[alt="image.jpg"]').trigger('click')
      await nextTick()
      expect(wrapper.get('header').classes()).toContain('opacity-100')

      await wrapper.get('button[aria-label="退出全屏"]').trigger('click')
      await nextTick()
      expect(wrapper.get('header').classes()).not.toContain('absolute')
      expect(wrapper.find('button[aria-label="进入全屏"]').exists()).toBe(true)
    } finally {
      wrapper.unmount()
    }
  })

  it('does not toggle controls when a zoomed image is dragged', async () => {
    const wrapper = mount(PawchiveMediaViewer, {
      attachTo: document.body,
      props: {
        post, attachment, attachments: [attachment], attachmentIndex: 0, attachmentTotal: 1,
        scopeLabel: 'Example', busy: false, error: '', hasPrevious: false, ended: false,
        autoplay: false, interval: 5, downloadBusy: false, downloadMessage: '', downloadError: false,
      },
    })
    const previousDescriptor = Object.getOwnPropertyDescriptor(document, 'fullscreenElement')
    Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: wrapper.element })
    try {
      await flushPromises()
      document.dispatchEvent(new Event('fullscreenchange'))
      await nextTick()
      await wrapper.get('button[title^="放大"]').trigger('click')
      const image = wrapper.get('img[alt="image.jpg"]').element
      const surface = image.parentElement!

      surface.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await nextTick()
      expect(wrapper.get('header').classes()).toContain('opacity-0')

      surface.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0, clientX: 100, clientY: 100 }))
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: 130, clientY: 100 }))
      window.dispatchEvent(new MouseEvent('mouseup', { clientX: 130, clientY: 100 }))
      surface.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await nextTick()
      expect(wrapper.get('header').classes()).toContain('opacity-0')
    } finally {
      Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: null })
      wrapper.unmount()
      if (previousDescriptor) Object.defineProperty(document, 'fullscreenElement', previousDescriptor)
      else Reflect.deleteProperty(document, 'fullscreenElement')
    }
  })

  it('retries a stalled image with a fresh ref, then skips it during autoplay', async () => {
    vi.useFakeTimers()
    const urls: string[] = []
    // First request hangs until the idle timeout aborts it; the retry fails outright.
    vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit) => {
      urls.push(url)
      if (urls.length > 1) return Promise.reject(new Error('offline'))
      return new Promise((_, reject) => init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))
    }))
    const reloadMedia = vi.fn(async () => true)
    const wrapper = mount(PawchiveMediaViewer, {
      props: {
        post, attachment, attachments: [attachment], attachmentIndex: 0, attachmentTotal: 1,
        scopeLabel: 'Example', busy: false, error: '', hasPrevious: false, ended: false,
        autoplay: true, interval: 5, downloadBusy: false, downloadMessage: '', downloadError: false,
        reloadMedia,
      },
    })
    try {
      await vi.advanceTimersByTimeAsync(19_000)
      expect(reloadMedia).not.toHaveBeenCalled()
      expect(wrapper.find('[role="status"]').text()).toContain('正在加载原图')
      await vi.advanceTimersByTimeAsync(1_000)
      expect(reloadMedia).toHaveBeenCalledTimes(1)
      expect(urls).toHaveLength(2)
      expect(urls[1]).not.toBe(urls[0])
      expect(urls[1]).toContain('retry=1')
      expect(wrapper.emitted('playbackError')?.at(-1)).toEqual(['图片加载失败，即将跳到下一项。'])
      await vi.advanceTimersByTimeAsync(2500)
      expect(wrapper.emitted('next')).toHaveLength(1)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('shows the thumbnail instead of retrying when the original is gone', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('missing', { status: 404 })))
    const reloadMedia = vi.fn(async () => true)
    const wrapper = mount(PawchiveMediaViewer, {
      props: {
        post, attachment, attachments: [attachment], attachmentIndex: 0, attachmentTotal: 1,
        scopeLabel: 'Example', busy: false, error: '', hasPrevious: false, ended: false,
        autoplay: true, interval: 5, downloadBusy: false, downloadMessage: '', downloadError: false,
        reloadMedia,
      },
    })
    try {
      await flushPromises()
      expect(wrapper.get('img[alt="image.jpg"]').attributes('src')).toContain('/external/pawchive/media/preview-ref')
      expect(wrapper.text()).toContain('来源站已缺失这张原图')
      expect(reloadMedia).not.toHaveBeenCalled()
      expect(wrapper.emitted('playbackError')).toBeUndefined()
    } finally {
      wrapper.unmount()
    }
  })

  it('keeps a slow original loading while bytes keep arriving', async () => {
    vi.useFakeTimers()
    let push: ((chunk: Uint8Array | null) => void) | undefined
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream<Uint8Array>({
      start(controller) { push = (chunk) => chunk ? controller.enqueue(chunk) : controller.close() },
    }), { status: 200, headers: { 'content-type': 'image/jpeg', 'content-length': '4' } })))
    const reloadMedia = vi.fn(async () => true)
    const wrapper = mount(PawchiveMediaViewer, {
      props: {
        post, attachment, attachments: [attachment], attachmentIndex: 0, attachmentTotal: 1,
        scopeLabel: 'Example', busy: false, error: '', hasPrevious: false, ended: false,
        autoplay: false, interval: 5, downloadBusy: false, downloadMessage: '', downloadError: false,
        reloadMedia,
      },
    })
    try {
      for (let second = 0; second < 3; second++) {
        await vi.advanceTimersByTimeAsync(15_000)
        push?.(new Uint8Array([1]))
      }
      await vi.advanceTimersByTimeAsync(15_000)
      expect(reloadMedia).not.toHaveBeenCalled()
      expect(wrapper.get('[role="status"]').text()).toContain('75%')
      push?.(new Uint8Array([1]))
      push?.(null)
      await vi.advanceTimersByTimeAsync(0)
      expect(wrapper.get('img[alt="image.jpg"]').attributes('src')).toBe('blob:image')
      expect(wrapper.emitted('playbackError')).toBeUndefined()
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })
})
