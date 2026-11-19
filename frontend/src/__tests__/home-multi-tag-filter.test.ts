import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'
import HomeView from '../views/HomeView.vue'
import { authState } from '../auth'
import type { Tag } from '../types'

const sampleTags: Tag[] = [
  { id: 1, name: '纯爱', namespace: 'general', count: 12 },
  { id: 2, name: '巨乳', namespace: 'general', count: 8 },
  { id: 3, name: 'NTR', namespace: 'general', count: 4 },
  { id: 4, name: 'Alice', namespace: 'artist', count: 5 },
]

describe('HomeView multi-tag, exclude-tag, and namespace filters', () => {
  const wrappers: ReturnType<typeof mount>[] = []

  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    authState.user = { id: 1, username: 'reader', is_admin: false, is_active: true, created_at: '' }
  })

  afterEach(() => {
    wrappers.forEach(w => w.unmount())
    wrappers.length = 0
    vi.restoreAllMocks()
  })

  it('supports multi-tag AND/OR, exclude tags, and namespace filtering in URL and API requests', async () => {
    const get = vi.spyOn(axios, 'get').mockImplementation(async (url) => ({
      data: String(url).endsWith('/tags') ? sampleTags : [],
      headers: { 'x-total-count': '0' },
    }))
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
    })
    await router.push('/')

    const wrapper = mount(HomeView, { global: { plugins: [router], stubs: { MediaDetail: true } } })
    wrappers.push(wrapper)
    await flushPromises()

    // Open tag dropdown
    await wrapper.get('button[aria-label="按标签筛选"]').trigger('click')
    await flushPromises()

    // Select first tag -> backward compatible single `tag` param
    const tagBtn = (name: string) => wrapper.findAll('#he-tag-options button').find(b => b.text().includes(name))!
    await tagBtn('纯爱').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.tag).toBe('纯爱')
    expect(router.currentRoute.value.query.tags).toBeUndefined()

    // Select second tag -> switches to `tags` + `tag_mode`
    await tagBtn('巨乳').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.tag).toBeUndefined()
    expect(router.currentRoute.value.query.tags).toBe('纯爱,巨乳')

    // Switch mode to OR (any)
    await tagBtn('任一(OR)').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.tag_mode).toBe('any')

    // Exclude NTR
    await wrapper.get('button[aria-label="排除标签 NTR"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.exclude_tags).toBe('NTR')

    // Filter by artist namespace
    await tagBtn('作者').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.tag_namespace).toBe('artist')

    const lastMediaCall = [...get.mock.calls].reverse().find(([url]) => String(url).endsWith('/media'))!
    expect(lastMediaCall[1]?.params).toMatchObject({
      tags: '纯爱,巨乳',
      tag_mode: 'any',
      exclude_tags: 'NTR',
      tag_namespace: 'artist',
    })
  })
})
