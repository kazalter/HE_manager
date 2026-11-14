import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'
import MediaCard from '../components/MediaCard.vue'
import HomeView from '../views/HomeView.vue'
import { authState } from '../auth'
import type { Media } from '../types'

const sampleMedia = (id = 1, overrides: Partial<Media> = {}): Media => ({
  id,
  title: `Sample ${id}`,
  relative_path: `sample-${id}.mp4`,
  media_type: 'video',
  extension: '.mp4',
  file_size: 1000,
  cover_path: `cover-${id}.jpg`,
  duration: 60,
  width: 640,
  height: 360,
  page_count: null,
  rating: 0,
  favorite: false,
  view_status: 'unviewed',
  progress: 0,
  last_opened_at: null,
  source_url: null,
  source_site: null,
  is_missing: false,
  missing_since: null,
  created_at: '',
  tags: [{ id: 1, name: 'tagA', namespace: 'general', count: 1 }],
  ...overrides,
})

describe('home performance optimizations', () => {
  const wrappers: ReturnType<typeof mount>[] = []

  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    wrappers.forEach(w => w.unmount())
    wrappers.length = 0
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('only sets eager loading on the first 12 media cards unless explicitly eager', () => {
    const first = mount(MediaCard, { props: { media: sampleMedia(1), index: 0 } })
    const twelfth = mount(MediaCard, { props: { media: sampleMedia(2), index: 11 } })
    const thirteenth = mount(MediaCard, { props: { media: sampleMedia(3), index: 12 } })
    const forcedEager = mount(MediaCard, { props: { media: sampleMedia(4), index: 20, eager: true } })
    wrappers.push(first, twelfth, thirteenth, forcedEager)

    expect(first.findAll('img').map(img => img.attributes('loading'))).toEqual(['eager', 'eager'])
    expect(twelfth.findAll('img').map(img => img.attributes('loading'))).toEqual(['eager', 'eager'])
    expect(thirteenth.findAll('img').map(img => img.attributes('loading'))).toEqual(['lazy', 'lazy'])
    expect(forcedEager.findAll('img').map(img => img.attributes('loading'))).toEqual(['eager', 'eager'])
  })

  it('throttles missing-file recheck across HomeView mounts', async () => {
    authState.user = { id: 1, username: 'admin', is_admin: true, is_active: true, created_at: '' }
    vi.spyOn(axios, 'get').mockImplementation(async (url) => ({
      data: String(url).endsWith('/tags') ? [] : [sampleMedia(1)],
      headers: { 'x-total-count': '1' },
    }))
    const post = vi.spyOn(axios, 'post').mockResolvedValue({ data: { recovered: 0 } } as any)

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
    })
    await router.push('/')

    const firstMount = mount(HomeView, { global: { plugins: [router], stubs: { MediaDetail: true } } })
    wrappers.push(firstMount)
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenCalledWith('/system/recheck-missing')

    // Remounting within cooldown does not trigger another recheck-missing POST.
    const secondMount = mount(HomeView, { global: { plugins: [router], stubs: { MediaDetail: true } } })
    wrappers.push(secondMount)
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('skips redundant /tags fetches when media updates do not change tags', async () => {
    authState.user = { id: 1, username: 'reader', is_admin: false, is_active: true, created_at: '' }
    const item = sampleMedia(1)
    const get = vi.spyOn(axios, 'get').mockImplementation(async (url) => ({
      data: String(url).endsWith('/tags') ? [] : [item],
      headers: { 'x-total-count': '1' },
    }))

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
    })
    await router.push('/')

    const wrapper = mount(HomeView, { global: { plugins: [router], stubs: { MediaDetail: true } } })
    wrappers.push(wrapper)
    await flushPromises()

    const tagCallsAfterMount = () => get.mock.calls.filter(([url]) => String(url).endsWith('/tags')).length
    expect(tagCallsAfterMount()).toBe(1)

    // Progress / rating update without tag changes must not refetch /tags.
    window.dispatchEvent(new CustomEvent('he:media-updated', {
      detail: { ...item, progress: 30, rating: 5 },
    }))
    await flushPromises()
    expect(tagCallsAfterMount()).toBe(1)

    // Tag change must refresh /tags.
    window.dispatchEvent(new CustomEvent('he:media-updated', {
      detail: { ...item, tags: [...item.tags, { id: 2, name: 'tagB', namespace: 'general', count: 1 }] },
    }))
    await flushPromises()
    expect(tagCallsAfterMount()).toBe(2)
  })
})
