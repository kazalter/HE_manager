import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, reactive, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'
vi.mock('../desktop', () => ({ desktopBridge: {}, desktopSession: reactive({ generation: 'library-session', revision: 1 }) }))
vi.mock('../composables/useCompactViewport', () => ({ useCompactViewport: () => ref(false) }))
vi.mock('../components/asyncComponents', () => ({ AsyncMediaDetail: defineComponent({ props: ['initialMedia', 'allMedia', 'hasAdjacentMediaPage', 'loadAdjacentMediaPage'], template: '<div class="opened-detail">{{ initialMedia.title }}</div>' }) }))
import HomeView from '../views/HomeView.vue'
import { authState } from '../auth'
const item = (id: number) => ({ id, title: 'Media ' + id, relative_path: `${id}.mp4`, media_type: 'video', cover_path: null, width: 640, height: 360, page_count: null, duration: 30, progress: 0, rating: 0, favorite: false, view_status: 'unviewed', tags: [], last_opened_at: null, created_at: '2026-10-18', is_missing: false })
let wrapper: ReturnType<typeof mount> | undefined
const response = (data: unknown, total = 62) => ({ data, headers: { 'x-total-count': String(total) } })
beforeEach(() => { localStorage.clear(); authState.token = ''; authState.user = { id: 1, username: 'test', is_admin: false, is_active: true, created_at: '' }; vi.restoreAllMocks() })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = '' })
async function create(detail?: (id: number) => Promise<any>) {
 const get = vi.spyOn(axios, 'get').mockImplementation(async (url, config: any) => {
  if (url === '/tags') return response([])
  if (url === '/media') return response(config?.params?.sort === 'opened' ? [] : Array.from({ length: config?.params?.offset ? 2 : 60 }, (_, i) => item(i + (config?.params?.offset || 0) + 1)))
  const id = /^\/media\/(\d+)$/.exec(String(url))?.[1]
  if (id) return detail ? detail(Number(id)) : response({ ...item(Number(id)), title: 'Verified ' + id, view_status: 'viewing', last_opened_at: '2026-10-18' })
  throw new Error('Unexpected request ' + url)
 })
 const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
 await router.push('/'); await router.isReady()
 wrapper = mount(HomeView, { attachTo: document.body, global: { plugins: [router], stubs: { MediaCard: defineComponent({ props: ['media'], emits: ['click'], template: '<button class="test-card" @click="$emit(\'click\')">{{ media.title }}</button>' }), DiscardContentDialog: true } } })
 await flushPromises(); return { get, router }
}
describe('desktop library contract', () => {
 it('requests bounded 60-item pages and viewing/opened continuation without opening cards during list load', async () => {
  const { get } = await create()
  expect(get).toHaveBeenCalledWith('/media', expect.objectContaining({ params: expect.objectContaining({ limit: 60, offset: 0 }) }))
  expect(get).toHaveBeenCalledWith('/media', expect.objectContaining({ params: expect.objectContaining({ sort: 'opened', view_status: 'viewing', limit: 12 }) }))
  expect(get.mock.calls.some(([url]) => /^\/media\/\d+$/.test(String(url)))).toBe(false)
  expect(wrapper!.text()).toContain('62 项')
  await wrapper!.get('button[aria-label="下一页"]').trigger('click'); await flushPromises()
  expect(get).toHaveBeenCalledWith('/media', expect.objectContaining({ params: expect.objectContaining({ limit: 60, offset: 60 }) }))
 })
 it('validates a local list item before mounting its viewer', async () => {
  let complete!: (value: any) => void
  const { get } = await create(() => new Promise(resolve => { complete = resolve }))
  await wrapper!.get('.test-card').trigger('click'); await flushPromises()
  expect(get).toHaveBeenCalledWith('/media/1', expect.objectContaining({ headers: { 'X-HE-Generation': 'library-session' } }))
  expect(wrapper!.find('.opened-detail').exists()).toBe(false)
  expect(document.body.textContent).not.toContain('正在打开作品')
  complete(response({ ...item(1), title: 'Verified first item' })); await flushPromises()
  expect(wrapper!.get('.opened-detail').text()).toBe('Verified first item')
 })
 it('drops a late detail result after the viewer is cancelled', async () => {
  let complete!: (value: any) => void
  const { router } = await create(() => new Promise(resolve => { complete = resolve }))
  await wrapper!.get('.test-card').trigger('click'); await flushPromises()
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); await flushPromises()
  complete(response({ ...item(1), title: 'Stale detail' })); await flushPromises()
  expect(wrapper!.find('.opened-detail').exists()).toBe(false); expect(router.currentRoute.value.query.media).toBeUndefined()
 })
})
