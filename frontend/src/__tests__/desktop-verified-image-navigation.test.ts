import { expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'

vi.mock('../desktop', () => ({ desktopBridge: {} }))
vi.mock('../auth', () => ({ authIdentity: () => 'test-user', authHeaders: () => ({}) }))
vi.mock('../config', () => ({ API_BASE_URL: '' }))
vi.mock('../components/MediaDetail.vue', () => ({ default: defineComponent({
  name: 'MediaDetail', props: ['initialMedia', 'allMedia', 'currentImageId'], emits: ['navigate'],
  template: '<div class="reader" @click="$emit(\'navigate\', allMedia[1])">{{ initialMedia.id }}</div>',
}) }))
import VerifiedMediaDetail from '../components/VerifiedMediaDetail.vue'

it('keeps the verified desktop image reader mounted through navigation and detail replacement', async () => {
  const images = [1, 2].map(id => ({ id, media_type: 'image', is_missing: false })) as any[]
  const wrapper = mount(VerifiedMediaDetail, { props: {
    initialMedia: images[0], allMedia: images, currentImageId: 1, verifiedForOpen: true,
  } })
  const original = wrapper.get('.reader').element
  await wrapper.get('.reader').trigger('click')
  expect(wrapper.emitted('navigate')?.[0]?.[0]).toEqual(images[1])
  expect(wrapper.get('.reader').element).toBe(original)
  await wrapper.setProps({ initialMedia: images[1], currentImageId: 2 })
  expect(wrapper.get('.reader').element).toBe(original)
  expect(wrapper.get('.reader').text()).toBe('2')
  wrapper.unmount()
})
