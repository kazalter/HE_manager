import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, reactive } from 'vue'
import axios from 'axios'
vi.mock('../desktop', () => ({ desktopBridge: {}, desktopSession: reactive({ generation: 'detail-identity', revision: 1 }) }))
vi.mock('../components/MediaDetail.vue', () => ({ default: defineComponent({ props: ['initialMedia'], emits: ['navigate'], template: '<button class="detail" @click="$emit(\'navigate\', {id: 2})">{{ initialMedia.title }}</button>' }) }))
import VerifiedMediaDetail from '../components/VerifiedMediaDetail.vue'
import { authState } from '../auth'
import type { Media } from '../types'
const media = (id: number, title = 'Cached ' + id) => ({ id, title } as Media)
let wrapper: ReturnType<typeof mount> | undefined
beforeEach(() => { vi.restoreAllMocks(); authState.user = { id: 1, username: 'test', is_admin: false, is_active: true, created_at: '' } })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = '' })
it('verifies a creator/recommendation item before mounting; DTO updates do not reopen it', async () => {
  let complete!: (value: unknown) => void
  const get = vi.spyOn(axios, 'get').mockImplementation(() => new Promise(resolve => { complete = resolve }))
  wrapper = mount(VerifiedMediaDetail, { props: { initialMedia: media(1), allMedia: [] }, attachTo: document.body })
  expect(wrapper.find('.detail').exists()).toBe(false)
  expect(document.body.textContent).not.toContain('正在打开作品')
  expect(document.querySelector('.fixed.inset-0')).toBeNull()
  expect(get).toHaveBeenCalledWith('/media/1', expect.objectContaining({ signal: expect.any(AbortSignal), headers: { 'X-HE-Generation': 'detail-identity' } }))
  complete({ data: media(1, 'Verified first') }); await flushPromises()
  expect(wrapper.get('.detail').text()).toBe('Verified first')
  await wrapper.setProps({ initialMedia: media(1, 'Metadata changed') }); await flushPromises()
  expect(get).toHaveBeenCalledOnce()
})
it('unmounts the old scene before navigation and discards late detail from the old item', async () => {
  const completions = new Map<string, (value: unknown) => void>()
  vi.spyOn(axios, 'get').mockImplementation(url => new Promise(resolve => { completions.set(String(url), resolve) }))
  wrapper = mount(VerifiedMediaDetail, { props: { initialMedia: media(1), allMedia: [] }, attachTo: document.body })
  completions.get('/media/1')!({ data: media(1) }); await flushPromises()
  await wrapper.get('.detail').trigger('click')
  expect(wrapper.find('.detail').exists()).toBe(false)
  expect(wrapper.emitted('navigate')).toEqual([[{ id: 2 }]])
  await wrapper.setProps({ initialMedia: media(2) })
  await wrapper.setProps({ initialMedia: media(3) })
  completions.get('/media/3')!({ data: media(3, 'Verified latest') }); await flushPromises()
  completions.get('/media/2')!({ data: media(2, 'Stale second') }); await flushPromises()
  expect(wrapper.get('.detail').text()).toBe('Verified latest')
})
it('aborts on close and never mounts a late response; already verified Home entry avoids a second GET', async () => {
  let complete!: (value: unknown) => void
  const get = vi.spyOn(axios, 'get').mockImplementation(() => new Promise(resolve => { complete = resolve }))
  wrapper = mount(VerifiedMediaDetail, { props: { initialMedia: media(1), allMedia: [] }, attachTo: document.body })
  const signal = get.mock.calls[0]![1]!.signal!
  wrapper.unmount(); wrapper = undefined
  expect(signal.aborted).toBe(true)
  complete({ data: media(1) }); await flushPromises()
  expect(document.querySelector('.detail')).toBeNull()
  wrapper = mount(VerifiedMediaDetail, { props: { initialMedia: media(2, 'Already verified'), allMedia: [], verifiedForOpen: true } })
  expect(wrapper.get('.detail').text()).toBe('Already verified')
  expect(get).toHaveBeenCalledOnce()
})
