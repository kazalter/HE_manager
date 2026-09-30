import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'
import HomeView from '../views/HomeView.vue'
import MobileNavigation from '../components/MobileNavigation.vue'
import { authState } from '../auth'

const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => {
  localStorage.clear(); sessionStorage.clear()
  authState.user = { id: 1, username: 'reader', is_admin: false, is_active: true, created_at: '' }
  vi.spyOn(axios, 'get').mockImplementation(async (url) => ({ data: String(url).endsWith('/tags') ? [] : [], headers: { 'x-total-count': '144' } }))
})
afterEach(() => { wrappers.forEach(wrapper => wrapper.unmount()); wrappers.length = 0; vi.restoreAllMocks() })
const routerFor = () => createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })

describe('mobile browsing continuity', () => {
  it('restores URL filters and page without resetting pagination when returning', async () => {
    const router = routerFor()
    await router.push('/?search=kept&tag=art&sort=rating&source=local&page=3')
    const wrapper = mount(HomeView, { global: { plugins: [router], stubs: { MediaDetail: true } } })
    wrappers.push(wrapper)
    await flushPromises()
    expect((wrapper.find('input[aria-label="搜索标题或文件名"]').element as HTMLInputElement).value).toBe('kept')
    expect(axios.get).toHaveBeenCalledWith('/media', expect.objectContaining({ params: expect.objectContaining({ offset: 72, search: 'kept', tag: 'art', sort: 'rating', source_site: 'local' }) }))
    expect(router.currentRoute.value.query.page).toBe('3')
    await router.push('/?favorite=true&page=2')
    await flushPromises()
    expect(axios.get).toHaveBeenLastCalledWith('/media', expect.objectContaining({ params: expect.objectContaining({ offset: 36, favorite: true, search: undefined }) }))
  })
  it('keeps independent library and favorite destinations while omitting viewer IDs', async () => {
    const router = routerFor()
    await router.push('/type/manga?page=2&media=8')
    const wrapper = mount(MobileNavigation, { global: { plugins: [router] } })
    wrappers.push(wrapper)
    await router.push('/?favorite=true&page=3')
    await flushPromises()
    const links = wrapper.findAll('a')
    expect(links[0]!.attributes('href')).toContain('/type/manga?page=2')
    expect(links[0]!.attributes('href')).not.toContain('media=')
    expect(links[2]!.attributes('href')).toContain('page=3')
    expect(links[2]!.attributes('aria-current')).toBe('page')
  })
  it('commits a dragged destination only on release and suppresses the synthetic click', async () => {
    const router = routerFor()
    await router.push('/')
    const wrapper = mount(MobileNavigation, { global: { plugins: [router] } })
    wrappers.push(wrapper)
    const surface = wrapper.get('.he-nav-surface')
    vi.spyOn(surface.element, 'getBoundingClientRect').mockReturnValue({ left: 0, width: 400 } as DOMRect)
    const pointer = { pointerId: 1, button: 0, isPrimary: true, clientY: 25 }
    await surface.trigger('pointerdown', { ...pointer, clientX: 50 })
    await surface.trigger('pointermove', { ...pointer, clientX: 355 })
    expect(router.currentRoute.value.path).toBe('/')
    expect(surface.classes()).toContain('is-dragging')
    await wrapper.findAll('a')[0]!.trigger('lostpointercapture', { pointerId: 1 })
    expect(surface.classes()).toContain('is-dragging')
    await surface.trigger('pointerup', { ...pointer, clientX: 355 })
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/more')
    await wrapper.findAll('a')[0]!.trigger('click', { button: 0, detail: 1 })
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/more')
  })
  it('cancels vertical or interrupted gestures and retains normal tap navigation', async () => {
    const router = routerFor()
    await router.push('/')
    const wrapper = mount(MobileNavigation, { global: { plugins: [router] } })
    wrappers.push(wrapper)
    const surface = wrapper.get('.he-nav-surface')
    vi.spyOn(surface.element, 'getBoundingClientRect').mockReturnValue({ left: 0, width: 400 } as DOMRect)
    const pointer = { pointerId: 1, button: 0, isPrimary: true }
    await surface.trigger('pointerdown', { ...pointer, clientX: 50, clientY: 25 })
    await surface.trigger('pointermove', { ...pointer, clientX: 55, clientY: 70 })
    await surface.trigger('pointerup', { ...pointer, clientX: 55, clientY: 70 })
    expect(router.currentRoute.value.path).toBe('/')
    await surface.trigger('pointerdown', { ...pointer, clientX: 50, clientY: 25 })
    await surface.trigger('pointermove', { ...pointer, clientX: 250, clientY: 25 })
    await surface.trigger('pointercancel', pointer)
    expect(surface.classes()).not.toContain('is-dragging')
    expect(router.currentRoute.value.path).toBe('/')
    await wrapper.findAll('a')[2]!.trigger('click', { button: 0, detail: 1 })
    await flushPromises()
    expect(router.currentRoute.value.query.favorite).toBe('true')
  })

})
