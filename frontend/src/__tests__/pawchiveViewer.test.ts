import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
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

describe('Pawchive fullscreen viewer', () => {
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
})
